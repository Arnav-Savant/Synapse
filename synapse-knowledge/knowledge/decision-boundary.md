---
id: decision-boundary
title: Decision Boundary
aliases: [separating hyperplane, classification boundary]
domains: [machine-learning, neural-networks]
status: stub
created: 2026-09-22
updated: 2026-09-22
sources: ["neural-networks/neuron-weights-and-bias.md"]
relationships:
  - type: related-to
    target: artificial-neuron
    note: a single neuron's linear combination defines a linear (hyperplane) decision boundary
---

# Decision Boundary

## What it is

A decision boundary is the surface in input space that separates the regions
a model assigns to different outcomes. For a single
[[artificial-neuron]] acting as a linear classifier, the boundary is where
the linear combination crosses zero:

$$\mathbf{W} \cdot \mathbf{X} + b = 0$$

That's a line in 2D and a hyperplane in higher dimensions.

## How the neuron's parameters shape it

- **Weights** set the boundary's **angle/orientation (slope)**. See
  [[weight-neural-networks]].
- **Bias** sets its **position (intercept)**, shifting it away from the
  origin. See [[bias-neural-networks]].

Without a bias, the boundary must pass through the origin. Data that needs a
boundary elsewhere then can't be separated. This is the geometric reason
neurons need a bias term.

## Beyond a single neuron

One neuron can only draw a straight (linear) boundary. Networks of many
neurons, with non-linear activation functions between layers, combine many
such boundaries to approximate very complex, non-linear ones. This is how
networks handle tasks like face recognition.

*Stub: currently covers only the linear, single-neuron case from the
source material.*
