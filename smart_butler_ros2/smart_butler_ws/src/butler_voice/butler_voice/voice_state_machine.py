"""Voice interaction state machine for MOSS robot.

Manages the voice interaction flow similar to smart speakers like XiaoAi:
IDLE -> WAKING -> LISTENING -> PROCESSING -> SPEAKING -> IDLE

Each state transition can trigger callbacks for:
- Sound effects
- LED indicators
- Logging
- External coordination
"""

import logging
import threading
import time
from enum import Enum
from typing import Optional, Callable, Dict, Any


class VoiceState(Enum):
    """Voice interaction states."""
    IDLE = "idle"                  # 待机状态，等待唤醒词
    WAKING = "waking"              # 唤醒词检测中
    LISTENING = "listening"        # 监听用户语音输入
    PROCESSING = "processing"      # 处理/识别语音
    SPEAKING = "speaking"          # 语音回复播放中
    ERROR = "error"                # 错误状态
    TIMEOUT = "timeout"            # 超时状态


class VoiceStateMachine:
    """Voice interaction state machine.

    Manages the flow of voice interactions with proper state transitions
    and callback notifications.

    Args:
        wake_word_timeout: Time to wait for wake word before returning to IDLE
        listening_timeout: Time to wait for speech before timeout
        processing_timeout: Time to wait for processing before timeout
        speaking_timeout: Time to wait for speaking before timeout
    """

    def __init__(
        self,
        wake_word_timeout: float = 30.0,
        listening_timeout: float = 10.0,
        processing_timeout: float = 30.0,
        speaking_timeout: float = 60.0,
    ):
        self._state = VoiceState.IDLE
        self._previous_state = VoiceState.IDLE
        self._lock = threading.RLock()

        # Timeouts
        self._wake_word_timeout = wake_word_timeout
        self._listening_timeout = listening_timeout
        self._processing_timeout = processing_timeout
        self._speaking_timeout = speaking_timeout

        # State timing
        self._state_enter_time = 0.0
        self._last_activity_time = 0.0

        # Callbacks
        self._on_state_change: Optional[Callable] = None
        self._on_state_enter: Dict[VoiceState, Callable] = {}
        self._on_state_exit: Dict[VoiceState, Callable] = {}

        # State-specific callbacks
        self._on_wake_word: Optional[Callable] = None
        self._on_speech_start: Optional[Callable] = None
        self._on_speech_end: Optional[Callable] = None
        self._on_recognition_result: Optional[Callable] = None
        self._on_speaking_start: Optional[Callable] = None
        self._on_speaking_end: Optional[Callable] = None
        self._on_error: Optional[Callable] = None
        self._on_timeout: Optional[Callable] = None

        # Context data
        self._context: Dict[str, Any] = {}

        # Timeout timer
        self._timeout_timer: Optional[threading.Timer] = None
        self._timeout_thread: Optional[threading.Thread] = None

        self._logger = logging.getLogger('voice_state_machine')

    @property
    def state(self) -> VoiceState:
        """Current state."""
        return self._state

    @property
    def previous_state(self) -> VoiceState:
        """Previous state."""
        return self._previous_state

    @property
    def state_duration(self) -> float:
        """Time spent in current state in seconds."""
        return time.time() - self._state_enter_time

    @property
    def time_since_activity(self) -> float:
        """Time since last activity in seconds."""
        return time.time() - self._last_activity_time

    @property
    def context(self) -> Dict[str, Any]:
        """Get current context data."""
        return self._context.copy()

    def set_context(self, key: str, value: Any):
        """Set context data."""
        self._context[key] = value

    def get_context(self, key: str, default: Any = None) -> Any:
        """Get context data."""
        return self._context.get(key, default)

    def clear_context(self):
        """Clear all context data."""
        self._context.clear()

    # ---- Callback registration --------------------------------------

    def on_state_change(self, callback: Callable):
        """Register callback for any state change.

        Callback signature: callback(old_state, new_state, context)
        """
        self._on_state_change = callback

    def on_state_enter(self, state: VoiceState, callback: Callable):
        """Register callback for entering a specific state.

        Callback signature: callback(context)
        """
        self._on_state_enter[state] = callback

    def on_state_exit(self, state: VoiceState, callback: Callable):
        """Register callback for exiting a specific state.

        Callback signature: callback(context)
        """
        self._on_state_exit[state] = callback

    def on_wake_word(self, callback: Callable):
        """Register callback for wake word detection.

        Callback signature: callback()
        """
        self._on_wake_word = callback

    def on_speech_start(self, callback: Callable):
        """Register callback for speech start.

        Callback signature: callback()
        """
        self._on_speech_start = callback

    def on_speech_end(self, callback: Callable):
        """Register callback for speech end.

        Callback signature: callback(audio_data)
        """
        self._on_speech_end = callback

    def on_recognition_result(self, callback: Callable):
        """Register callback for recognition result.

        Callback signature: callback(text, confidence)
        """
        self._on_recognition_result = callback

    def on_speaking_start(self, callback: Callable):
        """Register callback for speaking start.

        Callback signature: callback()
        """
        self._on_speaking_start = callback

    def on_speaking_end(self, callback: Callable):
        """Register callback for speaking end.

        Callback signature: callback()
        """
        self._on_speaking_end = callback

    def on_error(self, callback: Callable):
        """Register callback for error.

        Callback signature: callback(error_message)
        """
        self._on_error = callback

    def on_timeout(self, callback: Callable):
        """Register callback for timeout.

        Callback signature: callback(state)
        """
        self._on_timeout = callback

    # ---- State transitions ------------------------------------------

    def _transition(self, new_state: VoiceState, reason: str = ""):
        """Transition to a new state.

        Args:
            new_state: Target state
            reason: Reason for transition (for logging)
        """
        with self._lock:
            if self._state == new_state:
                return

            old_state = self._state
            self._previous_state = old_state

            # Cancel any pending timeout
            self._cancel_timeout()

            # Call exit callback for old state
            if old_state in self._on_state_exit:
                try:
                    self._on_state_exit[old_state](self._context)
                except Exception as e:
                    self._logger.error(f"Error in state exit callback: {e}")

            # Update state
            self._state = new_state
            self._state_enter_time = time.time()
            self._last_activity_time = time.time()

            # Log transition
            reason_str = f" ({reason})" if reason else ""
            self._logger.info(
                f"State transition: {old_state.value} -> {new_state.value}{reason_str}")

            # Call state change callback
            if self._on_state_change:
                try:
                    self._on_state_change(old_state, new_state, self._context)
                except Exception as e:
                    self._logger.error(f"Error in state change callback: {e}")

            # Call enter callback for new state
            if new_state in self._on_state_enter:
                try:
                    self._on_state_enter[new_state](self._context)
                except Exception as e:
                    self._logger.error(f"Error in state enter callback: {e}")

            # Start timeout timer if needed
            self._start_timeout_for_state(new_state)

    def _start_timeout_for_state(self, state: VoiceState):
        """Start timeout timer for the given state."""
        timeout = None
        if state == VoiceState.WAKING:
            timeout = self._wake_word_timeout
        elif state == VoiceState.LISTENING:
            timeout = self._listening_timeout
        elif state == VoiceState.PROCESSING:
            timeout = self._processing_timeout
        elif state == VoiceState.SPEAKING:
            timeout = self._speaking_timeout

        if timeout and timeout > 0:
            self._timeout_timer = threading.Timer(
                timeout, self._on_timeout_handler, args=(state,))
            self._timeout_timer.daemon = True
            self._timeout_timer.start()

    def _cancel_timeout(self):
        """Cancel any pending timeout timer."""
        if self._timeout_timer:
            self._timeout_timer.cancel()
            self._timeout_timer = None

    def _on_timeout_handler(self, state: VoiceState):
        """Handle timeout for a state."""
        self._logger.warning(f"Timeout in state: {state.value}")
        if self._on_timeout:
            try:
                self._on_timeout(state)
            except Exception as e:
                self._logger.error(f"Error in timeout callback: {e}")

        # Transition to TIMEOUT state, then back to IDLE
        self._transition(VoiceState.TIMEOUT, f"timeout in {state.value}")
        # Schedule return to IDLE (context will be cleared in to_idle)
        threading.Timer(1.0, lambda: self.to_idle("timeout recovery")).start()

    # ---- Public transition methods ----------------------------------

    def to_idle(self, reason: str = ""):
        """Transition to IDLE state."""
        self._context.clear()
        self._transition(VoiceState.IDLE, reason)

    def to_waking(self, reason: str = ""):
        """Transition to WAKING state (wake word detected)."""
        self._transition(VoiceState.WAKING, reason)
        if self._on_wake_word:
            try:
                self._on_wake_word()
            except Exception as e:
                self._logger.error(f"Error in wake word callback: {e}")

    def to_listening(self, reason: str = ""):
        """Transition to LISTENING state."""
        self._transition(VoiceState.LISTENING, reason)
        if self._on_speech_start:
            try:
                self._on_speech_start()
            except Exception as e:
                self._logger.error(f"Error in speech start callback: {e}")

    def to_processing(self, reason: str = ""):
        """Transition to PROCESSING state."""
        self._transition(VoiceState.PROCESSING, reason)

    def to_speaking(self, reason: str = ""):
        """Transition to SPEAKING state."""
        self._transition(VoiceState.SPEAKING, reason)
        if self._on_speaking_start:
            try:
                self._on_speaking_start()
            except Exception as e:
                self._logger.error(f"Error in speaking start callback: {e}")

    def to_error(self, error_message: str = "", reason: str = ""):
        """Transition to ERROR state."""
        self.set_context('error_message', error_message)
        self._transition(VoiceState.ERROR, reason or error_message)
        if self._on_error:
            try:
                self._on_error(error_message)
            except Exception as e:
                self._logger.error(f"Error in error callback: {e}")

    def to_timeout(self, reason: str = ""):
        """Transition to TIMEOUT state."""
        self._transition(VoiceState.TIMEOUT, reason)

    # ---- Event handlers ---------------------------------------------

    def on_wake_word_detected(self):
        """Called when wake word is detected."""
        if self._state == VoiceState.IDLE:
            self.to_waking("wake word detected")
            # Automatically transition to LISTENING after a short delay
            threading.Timer(0.5, lambda: self.to_listening("auto")).start()

    def on_speech_detected(self):
        """Called when speech is detected."""
        self._last_activity_time = time.time()
        if self._state == VoiceState.LISTENING:
            # Already listening, just update activity time
            pass

    def on_speech_ended(self, audio_data=None):
        """Called when speech ends."""
        if self._state == VoiceState.LISTENING:
            if audio_data is not None:
                self.set_context('audio_data', audio_data)
            if self._on_speech_end:
                try:
                    self._on_speech_end(audio_data)
                except Exception as e:
                    self._logger.error(f"Error in speech end callback: {e}")
            self.to_processing("speech ended")

    def on_recognition_complete(self, text: str, confidence: float = 1.0):
        """Called when recognition is complete."""
        if self._state == VoiceState.PROCESSING:
            self.set_context('recognized_text', text)
            self.set_context('confidence', confidence)
            if self._on_recognition_result:
                try:
                    self._on_recognition_result(text, confidence)
                except Exception as e:
                    self._logger.error(f"Error in recognition callback: {e}")

    def on_speaking_complete(self):
        """Called when speaking is complete."""
        if self._state == VoiceState.SPEAKING:
            if self._on_speaking_end:
                try:
                    self._on_speaking_end()
                except Exception as e:
                    self._logger.error(f"Error in speaking end callback: {e}")
            self.to_idle("speaking complete")

    def on_error_occurred(self, error_message: str):
        """Called when an error occurs."""
        self.to_error(error_message)

    # ---- Utility methods --------------------------------------------

    def is_idle(self) -> bool:
        """Check if in IDLE state."""
        return self._state == VoiceState.IDLE

    def is_listening(self) -> bool:
        """Check if in LISTENING state."""
        return self._state == VoiceState.LISTENING

    def is_processing(self) -> bool:
        """Check if in PROCESSING state."""
        return self._state == VoiceState.PROCESSING

    def is_speaking(self) -> bool:
        """Check if in SPEAKING state."""
        return self._state == VoiceState.SPEAKING

    def is_active(self) -> bool:
        """Check if in any active state (not IDLE or ERROR)."""
        return self._state not in (VoiceState.IDLE, VoiceState.ERROR, VoiceState.TIMEOUT)

    def get_state_info(self) -> Dict[str, Any]:
        """Get current state information."""
        return {
            'state': self._state.value,
            'previous_state': self._previous_state.value,
            'state_duration': self.state_duration,
            'time_since_activity': self.time_since_activity,
            'context': self._context.copy(),
        }

    def reset(self):
        """Reset the state machine to IDLE."""
        self._cancel_timeout()
        self._context.clear()
        self._state = VoiceState.IDLE
        self._previous_state = VoiceState.IDLE
        self._state_enter_time = time.time()
        self._last_activity_time = time.time()
        self._logger.info("State machine reset to IDLE")


class VoiceStateMachineROS2:
    """ROS2 integration for the voice state machine.

    Publishes state changes and provides ROS2 service interface.
    """

    def __init__(self, node, state_machine: VoiceStateMachine):
        self._node = node
        self._state_machine = state_machine

        # Publisher for state changes
        from std_msgs.msg import String
        self._state_pub = node.create_publisher(
            String, '/moss/voice/state', 10)

        # Register callbacks
        self._state_machine.on_state_change(self._on_state_change)

        self._logger = node.get_logger()

    def _on_state_change(self, old_state, new_state, context):
        """Publish state changes."""
        msg = String()
        msg.data = new_state.value
        self._state_pub.publish(msg)

    def get_state_machine(self) -> VoiceStateMachine:
        """Get the state machine instance."""
        return self._state_machine


def create_state_machine(
    wake_word_timeout: float = 30.0,
    listening_timeout: float = 10.0,
    processing_timeout: float = 30.0,
    speaking_timeout: float = 60.0,
) -> VoiceStateMachine:
    """Create a voice state machine with the given timeouts.

    Args:
        wake_word_timeout: Time to wait for wake word
        listening_timeout: Time to wait for speech
        processing_timeout: Time to wait for processing
        speaking_timeout: Time to wait for speaking

    Returns:
        VoiceStateMachine instance
    """
    return VoiceStateMachine(
        wake_word_timeout=wake_word_timeout,
        listening_timeout=listening_timeout,
        processing_timeout=processing_timeout,
        speaking_timeout=speaking_timeout,
    )


if __name__ == "__main__":
    # Test the state machine
    logging.basicConfig(level=logging.INFO)

    print("Testing voice state machine...")
    sm = create_state_machine()

    def on_change(old, new, ctx):
        print(f"State changed: {old.value} -> {new.value}")

    sm.on_state_change(on_change)

    # Simulate a voice interaction
    print("\nSimulating voice interaction:")
    print("1. Wake word detected")
    sm.on_wake_word_detected()
    time.sleep(0.6)

    print("2. Speech detected")
    sm.on_speech_detected()
    time.sleep(1)

    print("3. Speech ended")
    sm.on_speech_ended(audio_data=b"fake_audio")
    time.sleep(0.5)

    print("4. Recognition complete")
    sm.on_recognition_complete("打开客厅灯", 0.95)
    time.sleep(0.5)

    print("5. Speaking complete")
    sm.on_speaking_complete()
    time.sleep(0.5)

    print(f"\nFinal state: {sm.state.value}")
    print("Done!")
