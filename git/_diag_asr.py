import os, sys, time
os.chdir(r'C:\Users\LENOVO\Desktop\c++\ai')
sys.path.insert(0, '.')
from pathlib import Path
from app.core.config import load_env_file
load_env_file(Path('.env'))
import torch
print('CUDA:', torch.cuda.is_available(), torch.cuda.get_device_name(0))
print('VRAM free:', round((torch.cuda.get_device_properties(0).total_memory - torch.cuda.memory_allocated(0))/1024**3, 2), 'GB')
print('Importing ASR model...')
t0 = time.time()
from app.modules.asr.api import load_model
print('Loading...')
try:
    model = load_model()
    print(f'ASR loaded OK in {time.time()-t0:.1f}s')
    print('VRAM used:', round(torch.cuda.memory_allocated(0)/1024**3, 2), 'GB')
except Exception as e:
    print(f'FAIL in {time.time()-t0:.1f}s: {e}')
    import traceback
    traceback.print_exc()
