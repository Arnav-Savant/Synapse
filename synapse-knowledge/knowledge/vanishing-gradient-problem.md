---
id: vanishing-gradient-problem
title: Vanishing Gradient Problem
aliases: [vanishing gradients, vanishing gradient, gradient vanishing]
domains: [neural-networks, machine-learning]
status: stub
created: 2026-09-23
updated: 2026-09-23
sources: ["neural-networks/activation-functions-sigmoid-relu.md"]
relationships:
  - type: contrasts-with
    target: dead-neurons
    note: both stall learning through near-zero gradients; vanishing gradients are small, saturation-driven, and network-wide, while a dead ReLU neuron has an exactly-zero gradient and is permanently stuck
---

# Vanishing Gradient Problem

## What it is

Training updates each parameter in proportion to its gradient (slope). If
gradients get close to zero, the updates get close to zero too, and learning
slows down or stops.

## Main cause covered so far: saturating activations

The [[sigmoid-function]] flattens at very high and very low $z$, and a flat
curve has a slope near zero. A neuron whose $z$ lands in one of those
saturated regions barely changes during training. In a deep network with
sigmoid in the *hidden* layers, this nearly guarantees very slow training or
none at all.

## The standard remedy

Use [[relu]] in hidden layers. For $z > 0$ its gradient is a constant 1, so
it doesn't shrink the signal. ReLU fixes the problem only for positive
inputs. For negative inputs its gradient is exactly 0, and that leads to a
different problem, [[dead-neurons]].

## Vanishing gradients vs. dead neurons

| | Vanishing gradient | Dead (ReLU) neuron |
|---|---|---|
| Gradient | small but non-zero | exactly zero |
| Typical cause | saturating activations such as sigmoid | $z < 0$ for every input, e.g. a huge negative bias |
| Scope | slows learning across the network | one specific neuron |
| Recoverable? | slowly, in principle | no: permanently stuck |

*Stub: how gradients shrink as they flow back through many layers
(backpropagation and the chain rule), plus other remedies such as
initialization schemes and normalization, aren't covered by any source
material yet.*
