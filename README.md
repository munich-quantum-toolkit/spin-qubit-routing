# Routing Framework for Spin Qubits

This repository contains the implementation of the routing algorithms and
initial-mapping techniques described in the paper "_Routing Techniques for
Error-Corrected Silicon Spin Qubit Quantum Architectures_".

<p align="center">
  <a href="https://mqt.readthedocs.io/projects/sqr">
  <img width=30% src="https://img.shields.io/badge/documentation-blue?style=for-the-badge&logo=read%20the%20docs" alt="Documentation" />
  </a>
</p>

## Usage

Follow these steps to execute the framework:

1. Clone this repository using

   ```text
   git clone https://github.com/munich-quantum-toolkit/sqr.git
   ```

2. In [`examples/main.py`](./examples/main.py), select the desired
   initial-mapping and routing strategy, and adjust the `SimulationConfig` if
   needed.

3. Run the program by executing `uv run python examples/main.py`.

After that, a GUI should appear that visualizes the routing simulation:

<img width="659" height="556" alt="image" src="https://github.com/user-attachments/assets/7e75a36e-8c68-45e6-80ec-59c5cb7dae06" />
