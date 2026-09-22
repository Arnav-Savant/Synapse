---
id: relu
title: ReLU (Rectified Linear Unit)
aliases: [ReLU, rectified linear unit, rectifier, max(0, z)]
domains: [neural-networks, machine-learning]
status: developing
created: 2026-09-23
updated: 2026-09-23
sources: ["neural-networks/activation-functions-sigmoid-relu.md"]
relationships:
  - type: example-of
    target: activation-function
  - type: related-to
    target: vanishing-gradient-problem
    note: ReLU's constant gradient of 1 for positive inputs is the standard remedy for vanishing gradients
---

# ReLU (Rectified Linear Unit)

## What it is

The modern default [[activation-function]] for hidden layers:

$$f(z) = \max(0, z)$$

A negative input gives $0$. A positive input passes through unchanged.

## Why it wins over sigmoid

1. **No vanishing gradient for positive inputs.** For $z > 0$ the slope is a
   constant $1$. The gradient doesn't shrink the way it does in
   [[sigmoid-function]]'s flat tails. See [[vanishing-gradient-problem]].
2. **Compute efficiency.** There's no exponential, just one cheap check
   ("is $z < 0$?"). Sigmoid's $e^{-z}$ costs several CPU/GPU cycles.
3. **Sparsity.** ReLU sets every negative $z$ to *exactly* $0$, so large
   parts of the activation matrices are zeros. GPUs and TPUs can optimize
   sparse matrix multiplication by skipping the zero entries, which saves
   memory and time.

```python
relu(-50.0)     # 0.0: instant, and exactly zero (sparse)
sigmoid(-50.0)  # 1.93e-22: expensive, and never exactly zero
```

## Its failure mode: dying ReLU

The flat, zero-gradient region for $z < 0$ is also ReLU's weakness. Suppose
a neuron's weights and [[bias-neural-networks]] get pushed so that $z$ is
negative for *every* input, for example a very large negative bias. Then
ReLU always outputs 0, and its gradient is always 0. The neuron can't update
again and is permanently "dead". See [[dead-neurons]].

The sparsity that makes ReLU efficient and the dying-ReLU problem come from
the same property: the hard zero for negative inputs. Sparsity is healthy
when a neuron is zero for *some* inputs. The neuron is dead when it's zero
for *all* of them.

## Interview one-liner

ReLU is preferred over sigmoid in deep networks because it avoids vanishing
gradients for positive values, it's cheaper to compute (no exponential), and
it gives sparse activations that speed up matrix multiplication.
