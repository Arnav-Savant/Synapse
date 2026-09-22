---
id: dead-neurons
title: Dead Neurons
aliases: [dying ReLU, dead ReLU, dying neurons, dying ReLU problem]
domains: [neural-networks, machine-learning]
status: developing
created: 2026-09-22
updated: 2026-09-23
sources: ["neural-networks/neuron-weights-and-bias.md", "neural-networks/activation-functions-sigmoid-relu.md"]
relationships:
  - type: subtopic-of
    target: artificial-neuron
    note: a failure mode of an individual neuron
  - type: related-to
    target: bias-neural-networks
    note: a very large negative bias is one way a neuron dies
  - type: related-to
    target: relu
    note: the characteristic failure mode of ReLU, caused by its zero output and zero gradient for negative inputs
---

# Dead Neurons

## What it is

A dead neuron always outputs zero, whatever its input, and so stops
contributing to learning. With [[relu]] this is known as the **dying ReLU
problem**.

## How it happens

The source's example: a neuron's bias ([[bias-neural-networks]]) grows to a
huge negative value (e.g. $b = -10000$). Then its linear combination
$z = \mathbf{W} \cdot \mathbf{X} + b$ is strongly negative for every
realistic input. An activation function like ReLU maps every negative $z$ to
0, so the neuron's output is stuck at 0.

It's "permanent" because ReLU's gradient is also zero for negative inputs.
With no gradient flowing back, training can't adjust the neuron's weights or
bias to revive it.

This happens *through training itself*. The weight updates can push the bias
negative until $z < 0$ for every input, and at that point the updates stop
for good.

## The connection to bias

The bias is the one term in $z$ that doesn't depend on the input. So a
large negative bias drags $z$ below zero *uniformly*, for every example at
once. That's why the bias is the usual culprit: a single bad weight only
affects inputs where that feature is large, but a runaway bias shuts the
neuron off everywhere.

## Why it matters

A dead neuron is wasted capacity: its parameters still exist, but it
contributes nothing. If many neurons die, the network effectively gets
smaller.

## Not the same as vanishing gradients

Both stall learning through tiny gradients, but a dead ReLU's gradient is
*exactly* zero and the neuron is stuck permanently. Vanishing gradients
(e.g. from sigmoid saturation) are small but non-zero. See
[[vanishing-gradient-problem]].

## Healthy sparsity vs. death

ReLU outputs exactly 0 for negative inputs on purpose, and the resulting
sparsity is a performance benefit. A neuron that's zero for *some* inputs is
healthy. A neuron that's zero for *all* inputs is dead.

*Remedies (e.g. leaky ReLU, careful learning rates or initialization) aren't
yet covered by any source material.*
