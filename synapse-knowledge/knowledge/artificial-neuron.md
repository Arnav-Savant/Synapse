---
id: artificial-neuron
title: Artificial Neuron
aliases: [neuron, node, unit, perceptron unit]
domains: [neural-networks, machine-learning]
status: developing
created: 2026-09-22
updated: 2026-09-23
sources: ["neural-networks/neuron-weights-and-bias.md", "neural-networks/activation-functions-sigmoid-relu.md"]
relationships: []
---

# Artificial Neuron

## What it is

The artificial neuron is the smallest unit of computation in a neural
network. It's a mathematical function: it takes several numbers in, combines
them using learned parameters, and puts one number out.

It has three parts:

- **Inputs** $\mathbf{X} = [x_1, \dots, x_n]$: raw features (e.g. pixel
  intensities) or the outputs of neurons in the previous layer.
- **Weights** $\mathbf{W} = [w_1, \dots, w_n]$: one learned parameter per
  input, setting how much that input matters. See [[weight-neural-networks]].
- **Bias** $b$: one learned scalar per neuron, added to the weighted sum. See
  [[bias-neural-networks]].

## Why it matters

A single neuron is a linear classifier or regression unit: it makes one
weighted "micro-decision" over several variables. Wire thousands or millions
of them into a network (e.g. a multilayer perceptron) and those
micro-decisions combine to approximate very complex non-linear functions,
such as recognizing faces or translating text.

## How it works: the linear combination

This note covers the first step of a neuron's computation, the **linear
combination**. It comes before the activation function, which is what adds
non-linearity.

$$z = x_1 w_1 + x_2 w_2 + \dots + x_n w_n + b = \mathbf{W} \cdot \mathbf{X} + b$$

This is a dot product of inputs and weights, plus the bias. Frameworks like
PyTorch and TensorFlow don't loop over inputs. They vectorize the computation
as matrix multiplication, which GPUs parallelize efficiently, and they compute
whole layers of neurons at once.

```python
import numpy as np

class Neuron:
    def __init__(self, num_inputs):
        self.weights = np.random.randn(num_inputs)  # random init breaks symmetry
        self.bias = 0.0                             # bias commonly starts at 0

    def forward(self, inputs):
        return np.dot(inputs, self.weights) + self.bias  # z = W·X + b
```

The `np.random.randn` line matters. See [[weight-initialization]].

## Second step: the activation

The raw $z$ then goes through an [[activation-function]], $a = f(z)$, and
that $a$ is what the next layer receives. This step is what makes networks
more than linear: without it, any stack of neurons collapses into a single
linear transformation. The common choices are [[relu]] for hidden layers and
[[sigmoid-function]] for the output of a binary classifier.

## Mental model: deciding to buy a house

- **Inputs**: price, commute time, neighborhood safety.
- **Weights**: how much *you* care about each factor. Price might count a lot
  and commute time only a little.
- **Bias**: your baseline reluctance to move, which is a negative bias. Even
  with good inputs, the weighted sum has to overcome this reluctance before
  the answer is "yes".

## Geometric view

Treated as a classifier, the neuron draws a line (a hyperplane in higher
dimensions) through its input space. The weights set the line's angle and the
bias sets its position. See [[decision-boundary]].

## Parameter counting

A neuron with $n$ inputs has **$n$ weights and 1 bias**. So a neuron with 500
inputs has 500 weights and 1 bias.

## Failure modes

- **Dead neurons**: the output is pushed so negative that a following ReLU
  always outputs zero. See [[dead-neurons]].
- **Saturation**: with sigmoid, an extreme $z$ lands on a flat part of the
  curve and the neuron barely learns. See [[vanishing-gradient-problem]].
- **Symmetric initialization**: if all weights start at zero, every neuron
  computes the same thing. See [[weight-initialization]].

## Test yourself

1. If an input is irrelevant to the prediction, what will training likely do
   to its weight? *(Push it toward zero, so the input is effectively ignored.)*
2. Why isn't $z = \mathbf{W} \cdot \mathbf{X}$ enough? Why add $b$?
3. How many weights and biases does a neuron with 500 inputs have?
