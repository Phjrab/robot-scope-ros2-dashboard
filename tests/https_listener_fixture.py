"""Isolated dual-listener fixture; no dashboard/ROS imports or device access."""
import argparse
from contextlib import asynccontextmanager
import json
from pathlib import Path
from fastapi import FastAPI, Request, WebSocket
from robot_dashboard.https_listener import HttpsListener, run_with_https

if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    for key in ['http','https']:parser.add_argument('--'+key,type=int,required=True)
    for key in ['cert','key','receipt']:parser.add_argument('--'+key,required=True)
    args=parser.parse_args()
    counts={'startup':0,'shutdown':0}
    @asynccontextmanager
    async def lifespan(app):
        counts['startup']+=1
        try:yield
        finally:
            counts['shutdown']+=1
            Path(args.receipt).write_text(json.dumps(counts))
    app=FastAPI(lifespan=lifespan)
    @app.get('/health')
    async def health(request:Request):return {**counts,'scheme':request.url.scheme}
    @app.websocket('/ws')
    async def ws(socket:WebSocket):
        await socket.accept()
        await socket.send_text(await socket.receive_text())
        await socket.close()
    run_with_https(app,host='127.0.0.1',port=args.http,tls=HttpsListener('127.0.0.1',args.https,args.cert,args.key))
