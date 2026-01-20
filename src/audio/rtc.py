from typing import Optional

from aiortc.mediastreams import AudioStreamTrack
from av import AudioFrame

from contextlib import suppress
from datetime import datetime
from pathlib import Path
import av
import asyncio

from src.audio.utils import mix_audio_frames


class BaseMedia:
	def __init__(self) -> None:
		self._queues = {}

	async def callback(self, mixed: av.AudioFrame) -> None:
		raise NotImplementedError()

	async def recv(self) -> None:
		if len(self._queues) < 2:
			return
		if all(queue.qsize() > 1 for _, queue in self._queues.items()):
			frames = []
			for _, queue in self._queues.items():
				frame = await queue.get()
				frames.append(frame)
			mixed = mix_audio_frames(*frames)
			await self.callback(mixed)

	async def put(self, frame: av.AudioFrame, track: AudioStreamTrack) -> None:
		if not self._queues.get(track):
			self._queues.update({track: asyncio.Queue()})
		await self._queues[track].put(frame)
		await self.recv()


class MediaRecorder(BaseMedia):
	def __init__(self, file: Optional[Path] = None) -> None:
		file = file or Path("audio_logs") / datetime.now().strftime(
			"%Y-%m-%d-%H-%M-%S.mp3"
		)
		self.container = av.open(file=file, mode="w")
		self.stream = self.container.add_stream(codec_name="mp3")
		super().__init__()

	async def callback(self, mixed: av.AudioFrame) -> None:
		for packet in self.stream.encode(mixed):
			self.container.mux(packet)


class AudioRedirect(AudioStreamTrack):
	def __init__(self) -> None:
		self._queue = asyncio.Queue()
		super().__init__()

	async def recv(self) -> AudioFrame:
		frame = await self._queue.get()
		return frame


class MediaRedirect:
	def __init__(self, recorder: MediaRecorder) -> None:
		self.__audio = AudioRedirect()
		self.track: Optional[AudioStreamTrack] = None
		self.started = False
		self.task: Optional[asyncio.Task] = None
		self.recorder = recorder
		self.muted = False

	def add_track(self, track: AudioStreamTrack) -> None:
		self.track = track

	def mute(self) -> None:
		self.muted = True

	def unmute(self) -> None:
		self.muted = False

	@property
	def audio(self) -> AudioRedirect:
		return self.__audio

	async def start(self) -> None:
		if self.started or not self.track:
			return
		self.started = True
		self.task = asyncio.ensure_future(self.__run_track(self.track))

	async def stop(self) -> None:
		self.started = False
		if self.task:
			self.task.cancel()

	async def __run_track(self, track: AudioStreamTrack) -> None:
		while True:
			if self.muted:
				await asyncio.sleep(0.01)
				continue
			try:
				frame = await track.recv()
				await self.recorder.put(frame, self.__audio)
			except Exception as exc:
				print(exc)
				return
			with suppress(OSError):
				await self.__audio._queue.put(frame)
