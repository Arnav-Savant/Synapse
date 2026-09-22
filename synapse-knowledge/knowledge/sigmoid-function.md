---
id: sigmoid-function
title: Sigmoid Function
aliases: [sigmoid, logistic function, logistic sigmoid, σ(z)]
domains: [neural-networks, machine-learning]
status: developing
created: 2026-09-23
updated: 2026-09-23
sources: ["neural-networks/activation-functions-sigmoid-relu.md"]
relationships:
  - type: example-of
    target: activation-function
  - type: contrasts-with
    target: relu
    note: the classic squashing activation vs. the modern hidden-layer default; they differ in gradient behavior, cost, and sparsity
  - type: related-to
    target: vanishing-gradient-problem
    note: sigmoid's flat tails (saturation) are the textbook cause of vanishing gradients
---

# Sigmoid Function

## What it is

The "classic" [[activation-function]]:

$$\sigma(z) = \frac{1}{1 + e^{-z}}$$

It squashes any real input into the open range $(0, 1)$. Large positive $z$
approaches 1, large negative $z$ approaches 0, and $\sigma(0) = 0.5$.

## Where it's the right choice

The **final output layer of a binary classifier**. Its output reads naturally
as a probability. For example, $0.85$ means an 85% chance the positive class
is true.

## Where it's the wrong choice

- **Hidden layers of deep networks.** Novices often put sigmoid in middle
  layers. The network then trains very slowly or not at all, because of the
  [[vanishing-gradient-problem]]. Use [[relu]] there instead.
- **Unbounded regression outputs.** For a target like a house price ($50,000
  to $5,000,000), sigmoid on the output neuron is a serious mistake. Its
  output can never exceed 1, so the model physically can't produce the right
  answer.

## The fatal flaw: saturation

At very high or very low $z$, the sigmoid curve goes flat, and a flat curve
has a gradient (slope) near zero. Its derivative, $\sigma(z)(1 - \sigma(z))$,
peaks at only $0.25$ (at $z = 0$) and falls toward 0 in both tails. When a
neuron sits in a flat region, training barely updates it. Across many
sigmoid layers, those small factors shrink the gradient further.

## Compute cost

Computing $e^{-z}$ takes several expensive CPU/GPU cycles, compared with
ReLU's single comparison. Even when the answer is effectively zero, sigmoid
still does the full computation:

```python
sigmoid(-50.0)  # 1.9287498479639178e-22: tiny, but never exactly 0
```

Because sigmoid never outputs exactly 0, it doesn't produce the sparse
activations that ReLU does.
