# Transport layer — Companion Runtime communication protocol
#
# Architecture:
#   Frontend → Transport Protocol → CharacterRuntime.handle_turn()
#   CharacterRuntime.handle_turn() → Transport Protocol → Frontend
#
# Transport is a thin layer that serializes/deserializes messages
# between the Frontend and the Companion Runtime. It carries NO
# business logic — no LLM calls, memory operations, or character logic.
