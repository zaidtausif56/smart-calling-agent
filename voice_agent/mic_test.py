import wave, pyaudio, sys, time

p = pyaudio.PyAudio()
print("=== Device list ===")
for i in range(p.get_device_count()):
    d = p.get_device_info_by_index(i)
    print(i, d.get('name'), "in_channels:", d.get('maxInputChannels'), "defaultSampleRate:", d.get('defaultSampleRate'))

try:
    dev_info = p.get_default_input_device_info()
    device_index = dev_info['index']
except Exception as e:
    device_index = None
    print("Could not get default input device:", e)

FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 16000
CHUNK = 1024
RECORD_SECONDS = 5
OUT = "mic_test.wav"

if device_index is not None:
    print("Using device index:", device_index)

stream = p.open(format=FORMAT, channels=CHANNELS, rate=RATE,
                input=True, frames_per_buffer=CHUNK,
                input_device_index=device_index)

print("Recording for", RECORD_SECONDS, "seconds...")
frames = []
for i in range(0, int(RATE / CHUNK * RECORD_SECONDS)):
    data = stream.read(CHUNK, exception_on_overflow=False)
    print(f"chunk #{i} len={len(data)}")
    frames.append(data)

print("Stopping stream")
stream.stop_stream()
stream.close()
p.terminate()

wf = wave.open(OUT, 'wb')
wf.setnchannels(CHANNELS)
wf.setsampwidth(p.get_sample_size(FORMAT))
wf.setframerate(RATE)
wf.writeframes(b''.join(frames))
wf.close()
print("Saved", OUT)
