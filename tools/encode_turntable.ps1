# Encodes renders/turntable/frame_####.png into an MP4 (H.264) and a GIF preview.
$root = Split-Path -Parent $PSScriptRoot
$frames = Join-Path $root "renders\turntable\frame_%04d.png"
ffmpeg -y -framerate 30 -i $frames -c:v libx264 -pix_fmt yuv420p -crf 18 -movflags +faststart (Join-Path $root "renders\clerk_van_turntable.mp4")
ffmpeg -y -framerate 30 -i $frames -vf "fps=20,scale=960:-1:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=128[p];[s1][p]paletteuse=dither=bayer" (Join-Path $root "renders\clerk_van_turntable.gif")
