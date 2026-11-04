"""Copy to your Hosted App repo as scripts/ci_deploy_hosted.py. Uses App-scoped Deploy Token only."""
from __future__ import annotations
import argparse
import io
import json
import os
import re
import tarfile
import time
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit
from uuid import UUID


def load(root: Path) -> dict:
    cfg=json.loads((root/'deploy.json').read_text(encoding='utf-8'))
    origin=urlsplit(cfg['tenant_url'])
    if origin.scheme!='https' or not re.fullmatch(r'[a-z0-9][a-z0-9-]+\.ai-go\.app',origin.netloc) or origin.path not in {'','/'} or origin.query or origin.fragment:
        raise ValueError('部署目標必須是已確認的公司空間網址')
    cfg['app_id']=str(UUID(cfg['app_id']))
    public=urlsplit(cfg['public_url'])
    if public.scheme!='https' or not public.netloc.endswith('.ai-go.app') or public.username or public.password or public.path not in {'','/'} or public.query or public.fragment:
        raise ValueError('請先使用平台提供的 App 正式網址；自訂網域另行確認')
    if not isinstance(cfg.get('include'),list) or not cfg['include']:
        raise ValueError('需列出本次打包檔案與目錄')
    return cfg


def source_files(root: Path,cfg: dict) -> list[Path]:
    root=root.resolve(); out=set()
    for name in cfg['include']:
        rel=PurePosixPath(name)
        if not isinstance(name,str) or rel.is_absolute() or '..' in rel.parts or '\\' in name or ':' in name:
            raise ValueError('打包路徑不安全')
        source=root/name
        if not source.exists(): raise ValueError('打包清單缺檔')
        for p in ([source] if source.is_file() else source.rglob('*')):
            if p.is_symlink() or not p.resolve().is_relative_to(root): raise ValueError('打包不能含符號連結')
            if not p.is_file(): continue
            parts=p.relative_to(root).parts
            if any(s in {'.git','.aigo','node_modules','.venv'} or s.startswith('.env') for s in parts) or p.suffix.lower() in {'.pem','.key'}:
                raise ValueError('打包清單含憑證或開發環境目錄')
            if p.name=='.aigo-build.json': raise ValueError('版本識別檔由 CI 產生，不從本機帶入')
            out.add(p)
    if root/'Dockerfile' not in out or root/'VERSION' not in out:
        raise ValueError('打包必須包含 Dockerfile 與 VERSION')
    return sorted(out)


def tarball(root: Path,cfg: dict,commit: str) -> bytes:
    if not re.fullmatch(r'[0-9a-f]{40}',commit): raise ValueError('缺少本次完整 commit')
    root=root.resolve()
    files=source_files(root,cfg); buf=io.BytesIO()
    with tarfile.open(fileobj=buf,mode='w:gz') as tar:
        for path in files: tar.add(path,arcname=path.relative_to(root).as_posix(),recursive=False)
        marker=json.dumps({'commit':commit,'version':(root/'VERSION').read_text(encoding='utf-8').strip()}).encode()
        item=tarfile.TarInfo('.aigo-build.json'); item.size=len(marker)
        tar.addfile(item,io.BytesIO(marker))
    return buf.getvalue()


def deploy(root: Path,cfg: dict,commit: str) -> dict:
    import httpx
    token=os.environ.get('AIGO_DEPLOY_TOKEN','').strip()
    if not token: raise ValueError('請本人設定此 App 專用的 Actions secret AIGO_DEPLOY_TOKEN')
    blob=tarball(root,cfg,commit)
    base=cfg['tenant_url'].rstrip('/')+'/api/v1/hosted-apps/'+cfg['app_id']
    headers={'Authorization':'Bearer '+token}
    # Mutations have no automatic retry: timeout/429 is unknown, inspect first.
    with httpx.Client(timeout=90,follow_redirects=False) as client:
        response=client.post(base+'/deployments',headers=headers,json={}); response.raise_for_status()
        dep=response.json().get('latest_deployment') or response.json()
        dispatch=dep.get('dispatch') or {}
        upload=dispatch.get('deployd_upload_url','')
        if urlsplit(upload).scheme!='https' or not dispatch.get('upload_token'):
            raise ValueError('平台未提供有效上傳資訊；停止，不重新建立部署')
        response=client.post(upload,headers={'Authorization':'Bearer '+dispatch['upload_token']},
                             files={'tarball':('source.tar.gz',blob,'application/gzip')}); response.raise_for_status()
        deployment=str(UUID(response.json().get('deployment_id') or dep['id']))
        for _ in range(120):
            status=client.get(base+'/deployments/'+deployment,headers=headers); status.raise_for_status()
            state=status.json().get('status')
            if state=='active': break
            if state in {'failed','superseded'}: raise ValueError('部署未通過；先查平台紀錄，不自動重送')
            time.sleep(10)
        else: raise ValueError('等待逾時，部署結果未知；先查平台紀錄，不重新上傳')
        health=client.get(cfg['public_url'].rstrip('/')+'/health',timeout=60); health.raise_for_status()
        result=health.json()
        version=(root/'VERSION').read_text(encoding='utf-8').strip()
        if result.get('commit')!=commit or result.get('version')!=version:
            raise ValueError('正式網址仍不是本次版本；不能宣告完成')
        return {'deployment':'active','version':version,'commit':commit,'business_acceptance':'pending'}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--check',action='store_true')
    args=parser.parse_args(); root=Path(__file__).resolve().parents[1]
    try:
        cfg=load(root); source_files(root,cfg)
        result={'precheck':'passed'} if args.check else deploy(root,cfg,os.environ.get('GITHUB_SHA',''))
    except Exception as exc:
        print(json.dumps({'deployment':'not-confirmed','error':str(exc) if isinstance(exc,ValueError) else type(exc).__name__},ensure_ascii=False)); raise SystemExit(1)
    print(json.dumps(result,ensure_ascii=False))
