# easyqm
EasyApp application for running and visualizing quantum chemical calculations

## Assistant

The assistant panel (the robot button in the app bar, or Ctrl+Shift+A) answers questions about
the workspace and can change it. It has two optional parts:

| Extra | Install | Adds |
|---|---|---|
| `llm` | `pip install "EasyQM[llm]"` | Answers by Claude, with an Anthropic API key, `ANTHROPIC_API_KEY` or an `ant auth login` profile. Without it, an offline assistant answers. |
| `voice` | `pip install "EasyQM[voice]"` | Speech: talk to the assistant, and hear its answers. |

### Speech

Turn it on in the assistant settings (the gear in the panel header), under *Speech*:

- **Talk to the assistant.** Hold the microphone button beside Send, or Ctrl+Space in the input
  box, and speak. Release it to stop. The text appears in the input box and is sent after a
  moment; type or press Esc to correct it first.
- **Read answers aloud.** Answers are read with the system's voices. Talking, sending a new
  question, Esc or the speaker button stops the reading.

Speech is recognised on this computer: the recording is not sent or kept, only its text is sent,
as typed text would be. The first use downloads the speech model (about 140 MB); the settings
dialog shows where it goes. Recognition is English only for now. Design and limits:
`MD/LLM_INTEG_DESIGN.md`, §18.
