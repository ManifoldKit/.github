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
| [**ManifoldKit**](https://github.com/ManifoldKit/ManifoldKit) | Core: UI, runtime, persistence, and the in-core (cloud + Foundation) backends. |
| [**manifold-llama**](https://github.com/ManifoldKit/manifold-llama) | On-device GGUF / llama.cpp backend family. |
| [**manifold-mlx**](https://github.com/ManifoldKit/manifold-mlx) | On-device MLX backend family (text + image generation). |
| [**manifold-eval**](https://github.com/ManifoldKit/manifold-eval) | Independent assurance harness — reproducible, adversarial verdicts on `model × quant × backend × renderer` behavior. |

### Links

- 🌐 [manifoldkit.com](https://manifoldkit.com)
- 📘 [Documentation](https://docs.manifoldkit.com/documentation/manifoldkit/)
- 🚀 [Quickstart](https://github.com/ManifoldKit/ManifoldKit#hello-world) · iOS 18+ / macOS 15+ · Swift 6
