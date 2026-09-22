---
id: weight-neural-networks
title: Weight (Neural Networks)
aliases: [weights, weight, connection weight, synaptic weight]
domains: [neural-networks, machine-learning]
status: developing
created: 2026-09-22
updated: 2026-09-22
sources: ["neural-networks/neuron-weights-and-bias.md"]
relationships:
  - type: subtopic-of
    target: artificial-neuron
    note: one weight per input to a neuron
  - type: contrasts-with
    target: bias-neural-networks
    note: weights scale specific inputs and set the boundary's slope; the bias ignores the inputs and shifts the boundary
  - type: related-to
    target: decision-boundary
    note: weights set the boundary's angle/orientation
---

# Weight (Neural Networks)

## What it is

A weight is a learned parameter that scales one input to a neuron. A neuron
with $n$ inputs has a weight vector $\mathbf{W} = [w_1, \dots, w_n]$, and each
$w_i$ multiplies its $x_i$ in the neuron's linear combination
$z = \mathbf{W} \cdot \mathbf{X} + b$ (see [[artificial-neuron]]).

## What weights mean

A weight encodes **how important** its input is to the neuron's decision:

- A large magnitude means the input strongly influences $z$.
- The sign says whether the input pushes $z$ up or down.
- A weight **near zero** means the neuron effectively ignores that input. If
  a feature is irrelevant to the target, training tends to drive its weight
  toward zero.

In the house-buying analogy, the weights are how much you personally care
about price, commute time, and safety.

## Geometric role

When the neuron acts as a linear separator, the weights set the **angle (or
slope)** of the separating line or hyperplane. They cannot move the line away
from the origin. That's the bias's job. See [[decision-boundary]] and
[[bias-neural-networks]].

## Weight vs. bias (a common interview question)

- A **weight** belongs to one specific input feature. It sets that feature's
  influence and the slope of the decision boundary.
- A **bias** doesn't depend on any input. It shifts the whole decision
  boundary, so the model can fit data that doesn't pass through the origin.

## Practical notes

- Weights must be **randomly initialized**. Initializing them all to zero
  makes every neuron identical. See [[weight-initialization]].
- In practice, a layer's weights are stored as a matrix. The forward pass is
  a matrix multiplication, which GPUs run in parallel.
