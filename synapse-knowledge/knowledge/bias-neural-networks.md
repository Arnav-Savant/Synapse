---
id: bias-neural-networks
title: Bias (Neural Networks)
aliases: [bias, bias term, bias parameter, neuron bias]
domains: [neural-networks, machine-learning]
status: developing
created: 2026-09-22
updated: 2026-09-23
sources: ["neural-networks/neuron-weights-and-bias.md", "neural-networks/activation-functions-sigmoid-relu.md"]
relationships:
  - type: subtopic-of
    target: artificial-neuron
    note: one bias scalar per neuron
  - type: related-to
    target: decision-boundary
    note: the bias sets the boundary's position/intercept, so it doesn't have to pass through the origin
---

# Bias (Neural Networks)

> Not to be confused with *statistical bias* (as in the bias–variance
> tradeoff) or *dataset/algorithmic bias*. Here, "bias" is a model parameter.

## What it is

The bias $b$ is a learned **scalar** that each neuron adds to its weighted sum:

$$z = \mathbf{W} \cdot \mathbf{X} + b$$

Each neuron has exactly one bias, however many inputs it has. A neuron with
500 inputs has 500 weights and 1 bias. The bias is independent of the inputs,
so the neuron can output a non-zero value even when every input is zero.

## Why it's necessary

Picture the neuron as a line (or hyperplane) that separates data:

- The weights set the line's **angle/slope**.
- The bias sets its **intercept/position**.

Without a bias ($z = \mathbf{W} \cdot \mathbf{X}$), the boundary must pass
exactly through the origin. If the data can't be separated by a line through
the origin, a bias-free network can't learn the pattern, no matter how the
weights are trained. The bias gives the neuron an offset it can learn, like
the $c$ in $y = mx + c$. See [[decision-boundary]].

## Intuition

In the house-buying analogy, the bias is your **baseline reluctance to
move**. A negative bias sets a threshold: the weighted evidence (price,
commute, safety) has to overcome it before the neuron says "yes". A positive
bias would be a predisposition toward "yes".

## Initialization

A common convention (used in the source's reference implementation) is to
start biases at **0**. This is fine because the randomly initialized
*weights* already break symmetry between neurons. See
[[weight-initialization]].

## Failure mode: a runaway negative bias

If a bias becomes very negative (e.g. $b = -10000$), $z$ is strongly negative
for every realistic input. A following ReLU then always outputs 0, and the
neuron stops participating in learning. See [[dead-neurons]].

Because the bias shifts $z$ by the same amount for every input, it's the
parameter that can switch a [[relu]] neuron off everywhere at once. This is
the "dying ReLU" problem, and it can happen during training when weight
updates push the bias strongly negative.
