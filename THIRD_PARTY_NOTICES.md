# Third-party models and software

Sound Forge's own code is MIT-licensed. It downloads and drives the following, each under
its own licence. Check them before shipping a commercial game.

| Component | Used by | Licence | Outputs |
| :--- | :--- | :--- | :--- |
| Stable Audio 3 Small-SFX, Small-Music, Medium (Stability AI; ComfyUI repackage by Comfy-Org) | `sfx`, `ambience`, `stinger` | Stability AI Community License | Yours. Free for individuals and organisations under $1M annual revenue; commercial users must register with Stability; above $1M an Enterprise licence is needed. |
| T5Gemma text encoder (Google) | Stable Audio 3 | Gemma Terms of Use | - |
| ACE-Step 1.5 (ACE Studio / StepFun; ComfyUI repackage by Comfy-Org) | `music_loop`, `music_track` | MIT | The model card states generated music may be used commercially. |
| Qwen3-TTS 12Hz VoiceDesign / Base / Tokenizer (Alibaba Qwen) | `voice` | Apache 2.0 | - |
| ComfyUI-Qwen-TTS node pack (flybirdxx) | `voice` | see its repository | - |
| LAION CLAP `larger_clap_general` | ranking takes | Apache 2.0 | - |
| ComfyUI | everything | GPL-3.0 (run as a separate program) | - |
| pyloudnorm, soundfile, NumPy, SciPy | post-processing | MIT / BSD | - |

Voice cloning: only clone voices you have the right to use. Sound Forge clones only the
reference clips it designs itself from text descriptions, unless you replace them.
