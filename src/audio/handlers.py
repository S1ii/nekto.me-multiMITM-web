"""
WebRTC обработчики для аудио чата
"""
from contextlib import suppress
from typing import Dict, Any

from aiortc import RTCPeerConnection, RTCSessionDescription
from aiortc.contrib.media import MediaBlackhole
from aiortc.contrib.signaling import candidate_from_sdp

from src.audio.audio_client import AudioClient
from src.audio.rtc import MediaRedirect

import json


black_hole = MediaBlackhole()


def setup_webrtc_handlers(
    pc: RTCPeerConnection, 
    client: AudioClient, 
    redirect: MediaRedirect, 
    room
):
    """Настройка WebRTC обработчиков для peer connection"""
    log = client.log
    
    @pc.on("connectionstatechange")
    async def on_connection_state_change():
        from src.audio import DEBUG_MODE
        state = pc.connectionState
        if DEBUG_MODE:
            print(f"  🌐 [{client.name}] WebRTC state: {state}")
        
        if state == "connecting":
            pass
        elif state == "failed":
            log.error("WebRTC connection failed")
            await pc.close()
            await room.stop()
        elif state == "closed":
            log.info("WebRTC connection closed")
            await pc.close()
        elif state == "connected":
            if DEBUG_MODE:
                print(f"  ✅ [{client.name}] WebRTC connected!")
            # Проверяем что все участники подключены
            all_connected = all(
                m.pc and m.pc.connectionState == "connected" 
                for m in room.members
            )
            
            if all_connected:
                await black_hole.stop()
                if DEBUG_MODE:
                    print(f"  🎙️ All peers connected - starting audio recording")
                log.info("All peers connected - starting audio redirect")
                room.is_recording = True
                for member in room.members:
                    await member.redirect.start()
            else:
                await black_hole.start()
            
            # Отправляем подтверждение (если ещё подключены)
            if client.connection_id:
                payload = {
                    "type": "peer-connection",
                    "connectionId": client.connection_id,
                    "connection": True,
                }
                await client.emit("event", data=payload)
    
    @pc.on("track")
    async def on_track(track):
        log.info("Received audio track")
        room.add_members_track(track, client)
        black_hole.addTrack(track)
        
        # Подтверждаем получение стрима (если ещё подключены)
        if client.connection_id:
            payload = {
                "type": "stream-received",
                "connectionId": client.connection_id,
            }
            await client.emit("event", data=payload)
    
    # Регистрируем обработчики для клиента
    async def handle_peer_connect(client, payload):
        await on_peer_connect(client, payload, pc, redirect, room)
        
    async def handle_offer(client, payload):
        await on_offer(client, payload, pc, redirect, room)
        
    async def handle_answer(client, payload):
        await on_answer(client, payload, pc, redirect, room)
        
    async def handle_ice_candidate(client, payload):
        await on_ice_candidate(client, payload, pc, redirect, room)

    client.add_action("peer-connect", handle_peer_connect)
    client.add_action("offer", handle_offer)
    client.add_action("answer", handle_answer)
    client.add_action("ice-candidate", handle_ice_candidate)


async def on_peer_connect(
    client: AudioClient,
    payload: Dict[str, Any],
    pc: RTCPeerConnection,
    redirect: MediaRedirect,
    room,
):
    """Обработка peer-connect с инициацией WebRTC"""
    log = client.log
    initiator = payload.get("initiator", False)
    
    log.info(f"Peer connect event, initiator={initiator}")
    
    # Проверяем что другой участник тоже подключен
    with suppress(AttributeError):
        for member in room.members:
            if member.client.get_connection_id() != client.get_connection_id():
                break
        else:
            log.warning("Both clients have same connection_id, stopping room")
            await room.stop()
            return
    
    if initiator:
        # Мы инициатор - создаём offer
        pc.addTrack(redirect.audio)
        offer = await pc.createOffer()
        await pc.setLocalDescription(offer)
        
        # Отправляем peer-mute
        if client.connection_id:
            await client.emit("event", data={
                "type": "peer-mute",
                "connectionId": client.connection_id,
                "muted": False,
            })
        
        # Отправляем offer
        if client.connection_id:
            await client.emit("event", data={
                "type": "offer",
                "offer": json.dumps({"sdp": offer.sdp, "type": offer.type}),
                "connectionId": client.connection_id,
            })
            log.info("Sent WebRTC offer")


async def on_offer(
    client: AudioClient,
    payload: Dict[str, Any],
    pc: RTCPeerConnection,
    redirect: MediaRedirect,
    room,
):
    """Обработка входящего offer"""
    log = client.log
    
    # Проверяем состояние соединения
    if pc.signalingState == "closed" or pc.connectionState in ("closed", "failed"):
        log.warning(f"Ignoring offer - connection already {pc.signalingState}/{pc.connectionState}")
        return
    
    log.info("Received WebRTC offer")
    
    offer_data = json.loads(payload.get("offer", "{}"))
    remote_description = RTCSessionDescription(
        sdp=offer_data.get("sdp"),
        type=offer_data.get("type")
    )
    await pc.setRemoteDescription(remote_description)
    
    # Добавляем наш аудио трек
    pc.addTrack(redirect.audio)
    
    # Создаём и отправляем answer
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)
    
    if not client.connection_id:
        log.warning("No connection_id when sending answer")
        return
    
    await client.emit("event", data={
        "type": "answer",
        "answer": json.dumps({"sdp": answer.sdp, "type": answer.type}),
        "connectionId": client.connection_id,
    })
    log.info("Sent WebRTC answer")
    
    # Отправляем ICE кандидаты всем участникам
    with suppress(AttributeError):
        if all(m.client.connection_id for m in room.members):
            for member in room.members:
                await room.send_ice_candidates(member.pc, member.client)


async def on_answer(
    client: AudioClient,
    payload: Dict[str, Any],
    pc: RTCPeerConnection,
    redirect: MediaRedirect,
    room,
):
    """Обработка входящего answer"""
    log = client.log
    
    # Проверяем состояние соединения
    if pc.signalingState == "closed" or pc.connectionState in ("closed", "failed"):
        log.warning(f"Ignoring answer - connection already {pc.signalingState}/{pc.connectionState}")
        return
    
    log.info("Received WebRTC answer")
    
    answer_data = json.loads(payload.get("answer", "{}"))
    remote_description = RTCSessionDescription(
        sdp=answer_data.get("sdp"),
        type=answer_data.get("type")
    )
    await pc.setRemoteDescription(remote_description)
    
    # Отправляем ICE кандидаты
    with suppress(AttributeError):
        if all(m.client.connection_id for m in room.members):
            for member in room.members:
                await room.send_ice_candidates(member.pc, member.client)


async def on_ice_candidate(
    client: AudioClient,
    payload: Dict[str, Any],
    pc: RTCPeerConnection,
    redirect: MediaRedirect,
    room,
):
    """Обработка ICE кандидата"""
    log = client.log
    log.debug("Received ICE candidate")
    
    candidate_data = json.loads(payload.get("candidate", "{}")).get("candidate", {})
    candidate = candidate_from_sdp(candidate_data.get("candidate", ""))
    candidate.sdpMid = candidate_data.get("sdpMid")
    candidate.sdpMLineIndex = candidate_data.get("sdpMLineIndex")
    
    await pc.addIceCandidate(candidate)
