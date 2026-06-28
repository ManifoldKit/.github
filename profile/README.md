# ManifoldKit

**A full-stack, multi-backend AI chat framework for Apple platforms.** Import one umbrella
package and get a SwiftUI `ChatView`, the `ConversationRuntime` turn loop
(send / regenerate / edit / cancel / branch), SwiftData persistence, model download &
management UI, and inference backends spanning on-device (MLX, llama.cpp, Apple Foundation
Models) and cloud (OpenAI, Anthropic, Ollama, LAN) — all behind one `InferenceBackend` protocol.

Competitors ship a single layer; ManifoldKit ships the assembled product and the wiring
between layers.

### Packages

| Repo | What it is |
|------|------------|
| [**ManifoldKit**](https://github.com/roryford/ManifoldKit) | Core: UI, runtime, persistence, and the in-core (cloud + Foundation) backends. |
| [**manifold-llama**](https://github.com/roryford/manifold-llama) | On-device GGUF / llama.cpp backend family. |
| [**manifold-mlx**](https://github.com/roryford/manifold-mlx) | On-device MLX backend family (text + image generation). |

### Links

- 🌐 [manifoldkit.com](https://manifoldkit.com)
- 📘 [Documentation](https://roryford.github.io/ManifoldKit/documentation/manifoldkit/)
- 🚀 [Quickstart](https://github.com/roryford/ManifoldKit#hello-world) · iOS 18+ / macOS 15+ · Swift 6
