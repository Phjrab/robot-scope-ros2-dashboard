"""Direct HTTPS trust, shared lifespan, old HTTP and WebSocket regression."""
import asyncio
import json
import os
from pathlib import Path
import socket
import ssl
import subprocess
import sys
import tempfile
import time
import unittest
from urllib.error import URLError
from urllib.request import Request, urlopen
from robot_dashboard.https_listener import configured_https

class HttpsListenerTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.root=Path(temp.name).resolve();self.root.chmod(0o700)
        self.cert,self.key=self.root/'cert.pem',self.root/'key.pem'
        subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','1','-subj','/CN=localhost','-addext','subjectAltName=IP:127.0.0.1','-keyout',str(self.key),'-out',str(self.cert)],check=True,capture_output=True)
        self.key.chmod(0o600)
    def env(self,port=18443):
        return {'ROBOT_SCOPE_HTTPS_HOST':'127.0.0.1','ROBOT_SCOPE_HTTPS_PORT':str(port),'ROBOT_SCOPE_HTTPS_CERTFILE':str(self.cert),'ROBOT_SCOPE_HTTPS_KEYFILE':str(self.key),'ROBOT_SCOPE_EXPANSION_REVIEW_ORIGIN':f'https://127.0.0.1:{port}'}
    def test_off_partial_origin_bind_and_key_guards(self):
        self.assertIsNone(configured_https({},http_port=8088))
        self.assertEqual(configured_https(self.env(),http_port=8088).port,18443)
        for change in [{'ROBOT_SCOPE_HTTPS_KEYFILE':''},{'ROBOT_SCOPE_HTTPS_HOST':'0.0.0.0'},{'ROBOT_SCOPE_HTTPS_HOST':'8.8.8.8'},{'ROBOT_SCOPE_EXPANSION_REVIEW_ORIGIN':'http://127.0.0.1:18443'},{'ROBOT_SCOPE_HTTPS_PORT':'8088'}]:
            with self.subTest(change=change),self.assertRaises(ValueError):configured_https({**self.env(),**change},http_port=8088)
        self.key.chmod(0o644)
        with self.assertRaises(ValueError):configured_https(self.env(),http_port=8088)
    def test_real_trusted_tls_http_websockets_single_lifespan_and_shutdown(self):
        ports=[]
        for _ in range(2):
            with socket.socket() as s:s.bind(('127.0.0.1',0));ports.append(s.getsockname()[1])
        context=ssl.create_default_context(cafile=str(self.cert));receipt=self.root/'receipt.json'
        logfile=(self.root/'server.log').open('w');self.addCleanup(logfile.close)
        process=subprocess.Popen([sys.executable,'-m','tests.https_listener_fixture','--http',str(ports[0]),'--https',str(ports[1]),'--cert',str(self.cert),'--key',str(self.key),'--receipt',str(receipt)],stdout=logfile,stderr=subprocess.STDOUT)
        def cleanup():
            if process.poll() is None:process.terminate();process.wait(10)
        self.addCleanup(cleanup)
        base=f'https://127.0.0.1:{ports[1]}';deadline=time.monotonic()+12
        while True:
            try:
                with urlopen(base+'/health',context=context,timeout=1) as r:secure=json.load(r)
                break
            except (URLError,TimeoutError):
                if process.poll() is not None or time.monotonic()>deadline:self.fail((self.root/'server.log').read_text())
                time.sleep(.05)
        self.assertEqual(secure,{'startup':1,'shutdown':0,'scheme':'https'})
        with self.assertRaises(URLError):urlopen(base+'/health',timeout=2)
        req=Request(f'http://127.0.0.1:{ports[0]}/health',headers={'X-Forwarded-Proto':'https'})
        with urlopen(req,timeout=2) as r:self.assertEqual(json.load(r)['scheme'],'http')
        async def roundtrip():
            import websockets
            for url,options in [(f'ws://127.0.0.1:{ports[0]}/ws',{}),(f'wss://127.0.0.1:{ports[1]}/ws',{'ssl':context})]:
                async with websockets.connect(url,**options) as ws:
                    await ws.send('one loop');self.assertEqual(await ws.recv(),'one loop')
        asyncio.run(roundtrip());cleanup()
        self.assertEqual(process.returncode,0)
        self.assertEqual(json.loads(receipt.read_text()),{'startup':1,'shutdown':1})
    def test_occupied_listener_closes_other_listener_and_lifespan(self):
        with socket.socket() as occupied:
            occupied.bind(('127.0.0.1',0));occupied.listen()
            with socket.socket() as free:
                free.bind(('127.0.0.1',0));http=free.getsockname()[1]
            receipt=self.root/'failed-receipt.json'
            result=subprocess.run([sys.executable,'-m','tests.https_listener_fixture','--http',str(http),'--https',str(occupied.getsockname()[1]),'--cert',str(self.cert),'--key',str(self.key),'--receipt',str(receipt)],capture_output=True,text=True,timeout=12)
            self.assertNotEqual(result.returncode,0)
            self.assertIn('Dashboard listener startup failed',result.stderr)
            self.assertEqual(json.loads(receipt.read_text()),{'startup':1,'shutdown':1})
            with socket.socket() as probe:self.assertNotEqual(probe.connect_ex(('127.0.0.1',http)),0)
