import os, time, asyncio, subprocess, json
from helper.utils import metadata_text


async def _run_subprocess(cmd):
    """
    Run a subprocess WITHOUT blocking the asyncio event loop.
    Using asyncio.create_subprocess_exec instead of subprocess.run/check_output
    means other users' downloads/uploads/handlers keep running concurrently
    while ffmpeg/ffprobe are working.

    stdin is explicitly set to DEVNULL so ffmpeg can never sit waiting on an
    overwrite prompt it will never receive.
    """
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    return process.returncode, stdout, stderr


async def change_metadata(input_file, output_file, metadata):
    author, title, video_title, audio_title, subtitle_title = await metadata_text(metadata)

    # Get the video metadata (non-blocking, and errors are now handled instead of crashing)
    probe_cmd = ['ffprobe', '-v', 'error', '-show_streams', '-print_format', 'json', input_file]
    returncode, probe_out, probe_err = await _run_subprocess(probe_cmd)
    if returncode != 0:
        print("FFprobe Error:", probe_err.decode(errors="ignore"))
        return False

    try:
        data = json.loads(probe_out)
        streams = data['streams']
    except (json.JSONDecodeError, KeyError) as e:
        print("FFprobe output parse error:", e)
        return False

    # Create the FFmpeg command to change metadata
    cmd = [
        'ffmpeg',
        '-y',  # auto-overwrite output_file if it already exists (prevents an unattended hang)
        '-i', input_file,
        '-map', '0',  # Map all streams
        '-c:v', 'copy',  # Copy video stream
        '-c:a', 'copy',  # Copy audio stream
        '-c:s', 'copy',  # Copy subtitles stream
        '-metadata', f'title={title}',
        '-metadata', f'author={author}',
    ]

    # Add title to video stream
    for stream in streams:
        if stream['codec_type'] == 'video' and video_title:
            cmd.extend([f'-metadata:s:{stream["index"]}', f'title={video_title}'])
        elif stream['codec_type'] == 'audio' and audio_title:
            cmd.extend([f'-metadata:s:{stream["index"]}', f'title={audio_title}'])
        elif stream['codec_type'] == 'subtitle' and subtitle_title:
            cmd.extend([f'-metadata:s:{stream["index"]}', f'title={subtitle_title}'])

    cmd.extend(['-metadata', 'comment=Added by @Digital_Rename_Bot'])
    cmd.extend(['-f', 'matroska'])  # support all formats
    cmd.append(output_file)
    print(cmd)

    # Execute the command without blocking the event loop
    returncode, _, stderr = await _run_subprocess(cmd)
    if returncode != 0:
        print("FFmpeg Error:", stderr.decode(errors="ignore"))
        return False
    return True
