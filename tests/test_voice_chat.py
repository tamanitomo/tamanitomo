import io,json,sys,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
sys.path[:0]=[str(Path(__file__).resolve().parents[1]),str(Path(__file__).resolve().parents[1]/'kit/scripts')]
from tests.test_media_review import MediaReviewTests
from kit.app import voice_chat

class VoiceChatTests(MediaReviewTests):
    def test_audio_upload_auth_size_and_profile(self):
        self.assertEqual(self.client.post('/api/voice-chat/transcribe',content=b'x'*20,headers={'content-type':'audio/webm'}).status_code,401)
        headers={'x-companion-token':'secret','content-type':'audio/webm'}
        seen=[]
        def fake(rt,home,mode,payload):
            seen.append((home,mode,Path(payload['path'])));self.assertEqual(home.resolve(),self.c.home.resolve())
            return {'success':True,'transcript':'Hello there'}
        with patch.object(voice_chat,'bridge',side_effect=fake):
            r=self.client.post('/api/voice-chat/transcribe',content=b'x'*20,headers=headers)
            self.assertEqual(r.status_code,200,r.text)
            for _ in range(100):
                result=self.client.get('/api/operations/'+r.json()['id'],headers={'x-companion-token':'secret'}).json()
                if result.get('status')!='running':break
                time.sleep(.05)
            self.assertEqual(result.get('status'),'complete',result)
            self.assertEqual(result['result']['transcript'],'Hello there')
        self.assertFalse(seen[0][2].exists())
        self.assertEqual(self.client.post('/api/voice-chat/transcribe',content=b'x'*(voice_chat.MAX_AUDIO+1),headers=headers).status_code,413)
        self.assertEqual(self.client.get('/api/voice-chat/audio?name=../config.yaml',headers=headers).status_code,404)
    def test_voice_cache_cannot_cross_profiles_through_symlink(self):
        outside=Path(self.temp.name)/'elsewhere';outside.mkdir()
        try:(self.c.home/'.companion-voice').symlink_to(outside,target_is_directory=True)
        except OSError:self.skipTest('symlinks unavailable')
        response=self.post('voice-chat/speak',{'text':'Hello'})
        self.assertEqual(response.status_code,400)
