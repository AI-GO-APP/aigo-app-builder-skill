"""Read-only course scope preflight. This is not a server-side permission boundary."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID
from contextvars import ContextVar
from functools import wraps

_COURSE_WORKSPACE=ContextVar('aigo_course_workspace',default=None)

def course_project_operation(function):
    """Carry an explicit project scope through nested helpers without changing CWD/env."""
    @wraps(function)
    def wrapped(*args,**kwargs):
        project=kwargs.get('project_path') or (args[4] if len(args)>4 else None)
        root=course_workspace(project)
        state=_COURSE_WORKSPACE.set(root)
        try:return function(*args,**kwargs)
        finally:_COURSE_WORKSPACE.reset(state)
    return wrapped


def tenant_url(value: str) -> str:
    parsed = urlsplit(value)
    if (parsed.scheme != "https" or not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,61}[a-z0-9]\.ai-go\.app", parsed.netloc)
            or parsed.path not in {"", "/"} or parsed.query or parsed.fragment):
        raise ValueError("需使用明確的 https 租戶網址")
    return f"https://{parsed.netloc}"


def uuid_value(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("App／角色 id 必須為 UUID")
    return str(UUID(value))


def check_local(profile: dict, config: dict, effective_url: str, alias: str, kind: str = 'custom') -> dict:
    """Fail before authentication/network on unknown or overridden target."""
    if not isinstance(profile, dict) or not isinstance(config, dict):
        raise ValueError("工作區設定不是物件")
    base = tenant_url(profile["tenant_url"])
    if tenant_url(config["base_url"]) != base or tenant_url(effective_url) != base:
        raise ValueError("有效租戶與課程／工作區設定不一致，未執行平台操作")
    email = profile.get("student_email")
    configured_email = config.get("email")
    if (not isinstance(email, str) or "@" not in email or not isinstance(configured_email, str)
            or configured_email.casefold() != email.casefold()):
        raise ValueError("工作區身分與學員設定不一致")
    assignments = profile.get('apps', {}) if kind == 'custom' else profile.get('hosted_apps', {})
    if kind not in {'custom','hosted'} or not alias or alias not in assignments or alias not in config["apps"]:
        raise ValueError("必須明確指定已登錄的練習 App 別名")
    app = config["apps"][alias]
    assignment=assignments[alias]
    app_id = uuid_value(assignment if kind=='custom' else assignment.get('id'))
    if app.get("kind") != kind or uuid_value(app.get("id")) != app_id:
        raise ValueError("App id／產品線與練習設定不符")
    target={"tenant_url": base, "alias": alias, "app_id": app_id,
            "role_id": uuid_value(profile["role_id"]), "student_email": email.casefold()}
    if kind=='hosted':
        slug=assignment.get('slug')
        if not isinstance(slug,str) or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,61}[a-z0-9]',slug):
            raise ValueError('對外系統的 App 網址代稱未確認')
        if assignment.get('visibility') not in {'internal','public'}:
            raise ValueError('Hosted App 的預期可見度未確認')
        if assignment['visibility']=='public' and assignment.get('public_approved') is not True:
            raise ValueError('尚未確認本次公開內容與公開授權')
        target.update(kind='hosted',slug=slug,visibility=assignment['visibility'])
    return target


def check_identity(target: dict, me: dict) -> None:
    if (not isinstance(me, dict) or not isinstance(me.get("email"), str)
            or me["email"].casefold() != target["student_email"]):
        raise ValueError("登入身分不符；未讀取練習 App，不改用其他帳號")


def check_remote(target: dict, info: dict) -> dict:
    if not isinstance(info, dict) or uuid_value(info.get("id")) != target["app_id"]:
        raise ValueError("雲端 App 回讀不完整或 id 不一致")
    if info.get("access_mode") != "internal":
        raise ValueError("本題僅接受已確認的 internal Custom App")
    roles = info.get("access_role_ids")
    if (not isinstance(roles, list) or not roles
            or {uuid_value(role) for role in roles} != {target["role_id"]}):
        raise ValueError("專屬群組尚未確認；請學員在介面手動修正，不自動改權限")
    return {**target, "scope_check": "passed", "mutations": 0,
            "data_isolation_verified": False, "cross_role_access_verified": False}


def check_hosted_remote(target: dict, me: dict, info: dict) -> dict:
    check_identity(target,me)
    if uuid_value(info.get('id'))!=target['app_id'] or info.get('slug')!=target['slug']:
        raise ValueError('Hosted App id 或網址代稱與本題不符')
    if uuid_value(info.get('created_by'))!=uuid_value(me.get('id')):
        raise ValueError('Hosted App 不是目前學員建立的資源；請助教確認分配，不代改擁有者')
    if info.get('visibility')!=target['visibility']:
        raise ValueError('Hosted App 實際可見度與已確認範圍不符')
    roles=info.get('access_role_ids')
    if target['visibility']=='public':
        if roles!=[]: raise ValueError('公開 Hosted App 不應混用內部角色白名單')
    elif not isinstance(roles,list) or {uuid_value(r) for r in roles}!={target['role_id']}:
        raise ValueError('非公開 Hosted App 的專屬群組尚未確認')
    return {**target,'scope_check':'passed','mutations':0,'data_isolation_verified':False,
            'anonymous_access_verified':False,'server_authorization_verified':False}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--app", required=True)
    parser.add_argument('--kind',choices=['custom','hosted'],default='custom')
    args = parser.parse_args(argv)
    try:
        import aigo_auth as auth
        workspace = Path(args.workspace).resolve()
        # Exact workspace: no silent parent or global credential workspace selection.
        config = json.loads((workspace / ".aigo/config.json").read_text(encoding="utf-8"))
        profile = json.loads((workspace / ".aigo/learning.json").read_text(encoding="utf-8"))
        target = check_local(profile, config, auth.resolve_base_url(str(workspace)), args.app,args.kind)
        token = auth.get_token(str(workspace))
        import httpx
        response = httpx.get(f"{target['tenant_url']}/api/v1/auth/me",
                             headers={"Authorization": f"Bearer {token}"}, timeout=30)
        response.raise_for_status()
        me=response.json()
        check_identity(target,me)
        if args.kind=='hosted':
            response=httpx.get(f"{target['tenant_url']}/api/v1/hosted-apps/{target['app_id']}",
                               headers={"Authorization":f"Bearer {token}"},timeout=30)
            response.raise_for_status()
            result=check_hosted_remote(target,me,response.json())
        else:
            info = auth.get_app_info(target["tenant_url"], token, target["app_id"])
            result = check_remote(target, info)
    except Exception as exc:
        # HTTP errors can include sensitive bodies/URLs: print only class, never tokens/content.
        detail = str(exc) if isinstance(exc, (ValueError, KeyError, FileNotFoundError)) else type(exc).__name__
        print(json.dumps({"scope_check": "failed", "error": detail}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0




def course_workspace(workspace=None):
    """Course policy is opt-in; ordinary workspaces perform no extra API calls."""
    import os
    def locate(start):
        start=Path(start).resolve()
        for candidate in (start,*start.parents):
            marker=candidate/'AGENTS.md'
            if (candidate/'.aigo/learning.json').exists() or (marker.is_file() and '<!-- aigo-learning-workspace -->' in marker.read_text(encoding='utf-8',errors='replace')):
                return candidate
        return None
    found=locate(Path.cwd())
    explicit=workspace or _COURSE_WORKSPACE.get() or os.environ.get('AIGO_PROJECT_ROOT')
    if explicit:
        chosen=locate(explicit)
        if found is not None and chosen!=found:
            raise ValueError('目前課程工作區與指定工作區不同；停止操作，先核對目標')
        if chosen is not None: found=chosen
    return found


def guard_learning_write(base_url,token,*,app_id=None,slug=None,workspace=None):
    """Prevent accidental writes to another Custom App in a marked course workspace.

    This does not replace platform authorization, protect arbitrary HTTP calls,
    or prove row-level/anonymous data isolation.
    """
    root=course_workspace(workspace)
    if root is None: return {'course_scope':'not-applicable'}
    config=json.loads((root/'.aigo/config.json').read_text(encoding='utf-8'))
    profile=json.loads((root/'.aigo/learning.json').read_text(encoding='utf-8'))
    matches=[]
    for alias,assigned in profile.get('apps',{}).items():
        entry=config.get('apps',{}).get(alias,{})
        if app_id and assigned==app_id: matches.append(alias)
        elif not app_id and slug and entry.get('slug')==slug: matches.append(alias)
    if len(matches)!=1: raise ValueError('本次目標不是已確認的課程 Custom App；停止操作')
    target=check_local(profile,config,base_url,matches[0])
    import httpx
    response=httpx.get(target['tenant_url']+'/api/v1/auth/me',headers={'Authorization':'Bearer '+token},timeout=30)
    response.raise_for_status();check_identity(target,response.json())
    from aigo_auth import get_app_info
    info=get_app_info(base_url,token,target['app_id'])
    if slug and info.get('slug')!=slug: raise ValueError('雲端 App 與本次編譯目標不同')
    return check_remote(target,info)


if __name__ == "__main__":
    raise SystemExit(main())
