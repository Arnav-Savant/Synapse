---
id: backpropagation
title: Backpropagation
aliases: [backprop, backward pass, backpropagation of errors]
domains: [neural-networks, machine-learning]
status: stub
created: 2026-09-22
updated: 2026-09-22
sources: ["neural-networks/backpropagation-chain-rule-gradients.md"]
relationships:
  - type: related-to
    target: weight-neural-networks
    note: backprop computes the gradient of the loss with respect to each weight, which is what training uses to adjust it
  - type: prerequisite-of
    target: dead-neurons
    note: a dead neuron can't recover because backprop passes a zero gradient through its ReLU, so its parameters never get updated
  - type: related-to
    target: weight-initialization
    note: identical (e.g. all-zero) weights get identical gradients from backprop, which is why random initialization is needed to break symmetry
---

# Backpropagation

## What it is

Backpropagation is how a neural network works out how much each weight
contributed to its error. It computes the **gradient of the loss with
respect to each weight** ([[weight-neural-networks]]) by applying the
**chain rule** backwards through the network, **layer by layer**, from the
output back toward the inputs.

## Why it matters

A network's output depends on its weights through many nested functions:
each layer's output is the next layer's input. To train the network, you
need to know how nudging any single weight would change the loss.
Backpropagation gives you that for every weight at once. You get it by
walking the chain of nested functions in reverse, not by testing each
weight separately.

## How it works: the chain rule, backwards

The forward pass computes a chain of intermediate values: each
[[artificial-neuron]] computes $z = \mathbf{W} \cdot \mathbf{X} + b$, then an
activation $a = f(z)$, and that output feeds the next layer until the loss
$L$ comes out at the end. The chain rule says a derivative through a chain of
functions is the product of the local derivatives along it.

For a single weight $w_i$ of one neuron:

$$\frac{\partial L}{\partial w_i} = \frac{\partial L}{\partial a} \cdot \frac{\partial a}{\partial z} \cdot \frac{\partial z}{\partial w_i} = \frac{\partial L}{\partial a} \cdot f'(z) \cdot x_i$$

- $\partial L / \partial a$ says how the loss depends on this neuron's
  output. For a hidden neuron, that value comes from the layer after it,
  which is why the computation has to go **backwards**.
- $f'(z)$ is the local slope of the activation function.
- $\partial z / \partial w_i = x_i$, because $z$ is a linear combination.
  A weight's gradient is scaled by the input it multiplies.

The same pattern gives the bias's gradient. Since
$\partial z / \partial b = 1$, it is just $\frac{\partial L}{\partial a} \cdot f'(z)$.

Going layer by layer from the output, each layer reuses the gradient already
computed for the layer after it, multiplies in its own local derivatives, and
passes the result further back.

## Consequences worth knowing

- **Zero local slope blocks learning.** If $f'(z) = 0$, as with ReLU for
  negative $z$, the whole product is zero. The neuron's weights and bias get
  no gradient, so they can't change. This is why [[dead-neurons]] stay
  dead.
- **Identical neurons get identical gradients.** If all weights start equal
  (e.g. zero), every neuron in a layer computes the same $z$, receives the
  same gradient, and gets the same update. They stay copies of each other
  forever. See [[weight-initialization]].

## Test yourself

1. Why does backpropagation have to go from the output toward the input,
   rather than the other way?
2. In $\partial L / \partial w_i$, what factor comes from the input $x_i$,
   and what happens to the gradient if $x_i = 0$?
3. Why does a neuron whose ReLU always receives negative $z$ stop learning?

*Stub: the source material is a single-sentence definition. Loss functions,
gradient descent (how the gradients are actually used to update weights),
vanishing/exploding gradients, and a full multi-layer worked example are
not yet covered by any source.*
