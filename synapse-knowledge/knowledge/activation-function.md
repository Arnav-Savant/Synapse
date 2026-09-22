---
id: activation-function
title: Activation Function
aliases: [activation, activation functions, non-linearity, nonlinearity, transfer function]
domains: [neural-networks, machine-learning]
status: developing
created: 2026-09-23
updated: 2026-09-23
sources: ["neural-networks/activation-functions-sigmoid-relu.md"]
relationships:
  - type: subtopic-of
    target: artificial-neuron
    note: the second stage of a neuron's computation, applied to the linear combination z
  - type: related-to
    target: decision-boundary
    note: non-linear activations are what let a network learn curved, non-linear boundaries instead of a single hyperplane
---

# Activation Function

## What it is

An activation function is a mathematical "gate" at the end of an
[[artificial-neuron]]. The neuron first computes its linear combination

$$z = \mathbf{W} \cdot \mathbf{X} + b$$

and the activation function $f$ then transforms that raw $z$ into the
neuron's output $a = f(z)$, which is what gets passed to the next layer.

## Why it exists: the linearity trap

Stacking linear functions only ever produces another linear function. A
composition like $W_2(W_1 x + b_1) + b_2$ simplifies to a single $W' x + b'$.
So without activation functions, a network with 1,000 layers is
mathematically equivalent to one linear layer. It can only draw a single
straight [[decision-boundary]], however deep it is.

Activation functions introduce **non-linearity** by bending, squashing, or
thresholding $z$. That lets the network map curved, high-dimensional
boundaries, which tasks like image classification or translation need.

## The two covered so far

| | [[sigmoid-function]] | [[relu]] |
|---|---|---|
| Equation | $\sigma(z) = \frac{1}{1+e^{-z}}$ | $f(z) = \max(0, z)$ |
| Output range | $(0, 1)$ | $[0, \infty)$ |
| Typical place | final output layer of a binary classifier | hidden layers (the modern default) |
| Gradient | near zero at both extremes, so gradients vanish | constant 1 for $z > 0$, exactly 0 for $z < 0$ |
| Cost | needs an exponential | a single comparison |
| Main failure mode | [[vanishing-gradient-problem]] | [[dead-neurons]] ("dying ReLU") |

## Choosing one: rules of thumb

- **Hidden layers:** use ReLU. Sigmoid in hidden layers of a deep network
  almost guarantees slow training or no learning at all, because of vanishing
  gradients.
- **Output layer:** pick the activation to match the *range of the target*.
  Sigmoid fits a probability in $(0, 1)$. It's a serious mistake for an
  unbounded regression target like a house price ($50,000 to $5,000,000),
  because the output can never exceed 1.

## Implementation

```python
import numpy as np

def sigmoid(z):
    return 1 / (1 + np.exp(-z))

def relu(z):
    return np.maximum(0, z)
```

## Interview perspective

- **Q: Why do we need activation functions?** To introduce non-linearity.
  Without them, a deep network collapses into a single linear
  transformation.
- **Q: Why is ReLU preferred over sigmoid in deep networks?** It avoids
  vanishing gradients for positive inputs, it's cheaper (no exponential), and
  it produces sparse activations that hardware can exploit.

*Other activations (tanh, leaky ReLU, GELU, softmax) aren't covered by any
source material yet.*
