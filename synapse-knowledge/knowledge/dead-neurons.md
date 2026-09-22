---
id: dead-neurons
title: Dead Neurons
aliases: [dying ReLU, dead ReLU, dying neurons]
domains: [neural-networks, machine-learning]
status: stub
created: 2026-09-22
updated: 2026-09-22
sources: ["neural-networks/neuron-weights-and-bias.md"]
relationships:
  - type: subtopic-of
    target: artificial-neuron
    note: a failure mode of an individual neuron
  - type: related-to
    target: bias-neural-networks
    note: a very large negative bias is one way a neuron dies
---

# Dead Neurons

## What it is

A dead neuron always outputs zero, whatever its input, and so stops
contributing to learning.

## How it happens

The source's example: a neuron's bias ([[bias-neural-networks]]) grows to a
huge negative value (e.g. $b = -10000$). Then its linear combination
$z = \mathbf{W} \cdot \mathbf{X} + b$ is strongly negative for every
realistic input. An activation function like ReLU maps every negative $z$ to
0, so the neuron's output is stuck at 0.

It's "permanent" because ReLU's gradient is also zero for negative inputs.
With no gradient flowing back through [[backpropagation]], training can't
adjust the neuron's weights or bias to revive it.

## Why it matters

A dead neuron is wasted capacity: its parameters still exist, but it
contributes nothing. If many neurons die, the network effectively gets
smaller.

*Stub: ReLU and other activation functions aren't yet covered in depth.
Neither are remedies (e.g. leaky ReLU or careful learning rates).*
