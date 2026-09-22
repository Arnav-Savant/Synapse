---
id: weight-initialization
title: Weight Initialization
aliases: [parameter initialization, symmetry breaking, random initialization]
domains: [neural-networks, machine-learning]
status: stub
created: 2026-09-22
updated: 2026-09-22
sources: ["neural-networks/neuron-weights-and-bias.md"]
relationships:
  - type: subtopic-of
    target: weight-neural-networks
    note: how weights are set before training begins
  - type: related-to
    target: bias-neural-networks
    note: biases are also initialized, conventionally to zero, since random weights already break symmetry
---

# Weight Initialization

## What it is

Before training, a network's weights ([[weight-neural-networks]]) and
biases ([[bias-neural-networks]]) need starting values. How you choose them
matters.

## The key rule: break symmetry

If **every weight starts at zero**, every neuron in a layer gets the same
inputs, computes the same output, and so would be updated the same way.
The neurons stay identical copies and the layer never learns more than one
neuron's worth of features. Initializing weights **randomly** breaks this
symmetry, so each neuron can specialize.

The reference implementation from the source:

```python
self.weights = np.random.randn(num_inputs)  # random: breaks symmetry
self.bias = 0.0                             # zero is fine for biases
```

Biases can safely start at zero because the random weights already make each
neuron's output different.

*Stub: scaled initialization schemes (e.g. Xavier/Glorot, He) aren't yet
covered by any source material.*
