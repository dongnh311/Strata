# Tai Gyro-M (TQ2_0, 85.65 GB) + draft MTP (2.51 GB) ve D:\GitHub\Strata-data\models\Qwen3.8-Flash-Next-Gyro-GGUF
# Du cham/thanh lan: chay lai script nay la resume tu file .incomplete.
import sys, time
from huggingface_hub import hf_hub_download

repo = "agentionai/Qwen3.8-Flash-Next-Gyro-GGUF"
out = r"D:\GitHub\Strata-data\models\Qwen3.8-Flash-Next-Gyro-GGUF"
files = ["Qwen3.8-Flash-Next-Gyro-M-TQ2_0.gguf", "mtp-Qwen3.8-Flash-Next-draft.gguf"]

for fn in files:
    for attempt in range(3):
        t0 = time.time()
        p = hf_hub_download(repo_id=repo, filename=fn, local_dir=out)
        dt = time.time() - t0
        print(f"OK {fn} -> {p} ({dt:.0f}s)", flush=True)
        break
    else:
        print(f"FAIL {fn} sau 3 lan", flush=True)
        sys.exit(1)
print("ALL DONE", flush=True)
