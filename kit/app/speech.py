"""Provider-specific controls and Hermes command-provider adapters."""
import math
import os
from pathlib import Path
import shlex
import subprocess
import sys

LOCAL={'chatterbox':'chatterbox-tts','pockettts':'pocket-tts','qwen3tts':'qwen-tts','audio8':None}
REFERENCE={'neutts','chatterbox','pockettts','qwen3tts','audio8'}

def number(label,default,lo,hi,step=.05):return {'label':label,'type':'number','default':default,'min':lo,'max':hi,'step':step}
def string(label,default=''):return {'label':label,'type':'text','default':default}
def choice(label,values,default):return {'label':label,'type':'select','choices':values,'default':default}
SPEED=number('Speaking speed',1,.7,1.5)
DEVICE=choice('Compute device',['auto','cpu','cuda','mps'],'auto')
TEMP=number('Temperature',.8,.05,2)
TOPP=number('Top P',.95,.05,1)
SEED=number('Seed (−1 random)',-1,-1,2147483647,1)
FIELDS={
 'edge':{'speed':SPEED},
 'openai':{'speed':SPEED,'model':string('Model','gpt-4o-mini-tts'),'base_url':string('Custom API base URL')},
 'xai':{'speed':SPEED},
 'elevenlabs':{'model':string('Model','eleven_multilingual_v2')},
 'minimax':{'speed':SPEED,'pitch':number('Pitch',0,-12,12,1),'emotion':choice('Emotion',['neutral','happy','sad','angry','fearful','disgusted','surprised'],'neutral')},
 'gemini':{'model':string('Model','gemini-2.5-flash-preview-tts')},'mistral':{'model':string('Model','voxtral-mini-tts-2603')},
 'neutts':{},'kittentts':{'speed':SPEED},
 'piper':{'length_scale':number('Length scale (higher = slower)',1,.1,3),'noise_scale':number('Voice variation',.667,0,2),'noise_w_scale':number('Phoneme variation',.8,0,2),'volume':number('Volume',1,0,2),'speaker_id':number('Speaker ID',0,0,10000,1)},
 'chatterbox':{'device':DEVICE,'exaggeration':number('Expressiveness',.5,0,2),'cfg_weight':number('Guidance weight',.5,0,1),'temperature':TEMP,'top_p':TOPP,'repetition_penalty':number('Repetition penalty',1.2,1,3),'seed':SEED},
 'pockettts':{'language':choice('Language',['english','french_24l','german','german_24l','portuguese','portuguese_24l','italian','italian_24l','spanish','spanish_24l'],'english'),'device':choice('Compute device',['cpu','cuda','mps'],'cpu'),'temperature':number('Temperature',.3,.05,2),'sampler_decode_steps':number('Decode steps',1,1,10,1),'eos_threshold':number('End-of-speech threshold',-4,-10,0,.1)},
 'qwen3tts':{'device':DEVICE,'model':string('Model','Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice'),'mode':choice('Voice mode',['custom','clone','design'],'custom'),'language':string('Language','English'),'instruct':string('Voice direction'),'temperature':TEMP,'top_p':TOPP,'seed':SEED},
 'audio8':{'device':DEVICE,'model':string('Model','Audio8/Audio8-TTS-Preview-0.6b'),'temperature':TEMP,'top_p':TOPP,'top_k':number('Top K',50,0,1000,1),'max_new_tokens':number('Maximum audio tokens',1024,64,2000,1),'seed':SEED},
}
LABELS={'edge':'Edge · online','piper':'Piper · local','kittentts':'KittenTTS · local','neutts':'NeuTTS · local','openai':'OpenAI','xai':'xAI / Grok','elevenlabs':'ElevenLabs','minimax':'MiniMax','gemini':'Gemini','mistral':'Mistral','chatterbox':'Chatterbox · local','audio8':'Audio8 · local','pockettts':'Pocket TTS · local CPU','qwen3tts':'Qwen3-TTS · local'}

def validate(provider,values):
    if provider not in FIELDS:raise ValueError('Unknown speech engine')
    if not isinstance(values,dict) or set(values)-set(FIELDS[provider]):raise ValueError('Unsupported controls for this provider')
    clean={}
    for key,value in values.items():
        field=FIELDS[provider][key]
        if field['type']=='number':
            if isinstance(value,bool):raise ValueError('Invalid '+field['label'])
            try:value=float(value)
            except (TypeError,ValueError):raise ValueError('Invalid '+field['label'])
            if not math.isfinite(value) or not field['min']<=value<=field['max']:raise ValueError('Out of range: '+field['label'])
            if field['step']==1:
                if not value.is_integer():raise ValueError('Use a whole number for '+field['label'])
                value=int(value)
        else:
            if not isinstance(value,str) or len(value)>2000 or '\0' in value:raise ValueError('Invalid '+field['label'])
            if field['type']=='select' and value not in field['choices']:raise ValueError('Invalid '+field['label'])
        clean[key]=value
    return clean

def engine_python(root,provider):return root/'companion-engines'/provider/'venv'/('Scripts/python.exe' if os.name=='nt' else 'bin/python')

def command(root,home,provider):
    python=engine_python(root,provider)
    script=Path(__file__).resolve().parents[1]/'scripts/companion_tts_adapter.py'
    args=[str(python),str(script),'--home',str(home),'--provider',provider,'--input','{input_path}','--output','{output_path}']
    return subprocess.list2cmdline(args) if os.name=='nt' else shlex.join(args)

def configure(cfg,root,home,provider,voice,controls,transcript):
    tts=cfg.setdefault('tts',{});tts['provider']=provider
    block=tts.setdefault(provider,{})
    block.update(controls)
    block['voice_id' if provider in ('xai','elevenlabs','minimax','mistral') else 'voice']=voice
    if provider in REFERENCE:block['ref_text']=transcript
    if provider in LOCAL:
        tts.setdefault('providers',{})[provider]={'type':'command','command':command(root,home,provider),'output_format':'wav','voice_compatible':True,'timeout':600,'max_text_length':1000}

def install(rt,provider,report):
    if provider not in LOCAL:raise ValueError('Unknown local speech engine')
    folder=rt.root/'companion-engines'/provider;python=engine_python(rt.root,provider)
    folder.mkdir(parents=True,exist_ok=True)
    def run(argv,timeout=900):
        from .runtime import redact
        r=subprocess.run(argv,capture_output=True,text=True,stdin=subprocess.DEVNULL,timeout=timeout)
        if r.returncode:raise ValueError(redact(r.stderr or r.stdout)[-4000:])
    if not python.is_file():
        report('Creating an isolated '+provider+' environment on the Hermes host')
        import shutil
        uv=shutil.which('uv')
        if uv:run([uv,'venv','--python','3.11','--seed',str(folder/'venv')],180)
        else:run([sys.executable,'-m','venv',str(folder/'venv')],120)
    report('Installing '+provider+'. Model weights download on first preview.')
    if provider=='audio8':
        repo=folder/'Audio8_TTS'
        if not repo.exists():run(['git','clone','--depth','1','https://github.com/Edge0-AI/Audio8_TTS.git',str(repo)],180)
        run([str(python),'-m','pip','install','-r',str(repo/'requirements.txt'),'PyYAML'])
    else:run([str(python),'-m','pip','install',LOCAL[provider],'PyYAML','soundfile'])
    return {'note':provider+' installed beside Hermes. Save the voice, then generate a preview.'}
