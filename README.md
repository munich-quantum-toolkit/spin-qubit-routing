[![PyPI](https://img.shields.io/pypi/v/mqt.sqr?logo=pypi&style=flat-square)](https://pypi.org/project/mqt.sqr/)
![OS](https://img.shields.io/badge/os-linux%20%7C%20macos%20%7C%20windows-blue?style=flat-square)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg?style=flat-square)](https://opensource.org/licenses/MIT)
[![CI](https://img.shields.io/github/actions/workflow/status/munich-quantum-toolkit/sqr/ci.yml?branch=main&style=flat-square&logo=github&label=ci)](https://github.com/munich-quantum-toolkit/sqr/actions/workflows/ci.yml)
[![CD](https://img.shields.io/github/actions/workflow/status/munich-quantum-toolkit/sqr/cd.yml?style=flat-square&logo=github&label=cd)](https://github.com/munich-quantum-toolkit/sqr/actions/workflows/cd.yml)
[![Documentation](https://img.shields.io/readthedocs/mqt-sqr?logo=readthedocs&style=flat-square)](https://mqt.readthedocs.io/projects/sqr)
[![codecov](https://img.shields.io/codecov/c/github/munich-quantum-toolkit/sqr?style=flat-square&logo=codecov)](https://codecov.io/gh/munich-quantum-toolkit/sqr)

<p align="center">
  <a href="https://mqt.readthedocs.io">
    <picture>
      <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/munich-quantum-toolkit/.github/refs/heads/main/docs/_static/logo-mqt-dark.svg" width="60%">
      <img src="https://raw.githubusercontent.com/munich-quantum-toolkit/.github/refs/heads/main/docs/_static/logo-mqt-light.svg" width="60%" alt="MQT Logo">
    </picture>
  </a>
</p>

# MQT SQR - A Tool for Spin Qubit Routing

MQT SQR is a tool for spin qubit routing. It is part of the
[_Munich Quantum Toolkit (MQT)_](https://mqt.readthedocs.io).

<p align="center">
  <a href="https://mqt.readthedocs.io/projects/sqr">
  <img width=30% src="https://img.shields.io/badge/documentation-blue?style=for-the-badge&logo=read%20the%20docs" alt="Documentation" />
  </a>
</p>

## Key Features

> [!NOTE]
> MQT SQR is still in active development.

If you have any questions, feel free to create a
[discussion](https://github.com/munich-quantum-toolkit/sqr/discussions) or an
[issue](https://github.com/munich-quantum-toolkit/sqr/issues) on
[GitHub](https://github.com/munich-quantum-toolkit/sqr).

## Contributors and Supporters

The _[Munich Quantum Toolkit (MQT)](https://mqt.readthedocs.io)_ is developed by
the [Chair for Design Automation](https://www.cda.cit.tum.de/) at the
[Technical University of Munich](https://www.tum.de/) and supported by
[MQSC](https://mq.sc). Among others, it is part of the
[Munich Quantum Software Stack (MQSS)](https://www.munich-quantum-valley.de/research/research-areas/mqss)
ecosystem, which is being developed as part of the
[Munich Quantum Valley (MQV)](https://www.munich-quantum-valley.de) initiative.

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/munich-quantum-toolkit/.github/refs/heads/main/docs/_static/mqt-logo-banner-dark.svg" width="90%">
    <img src="https://raw.githubusercontent.com/munich-quantum-toolkit/.github/refs/heads/main/docs/_static/mqt-logo-banner-light.svg" width="90%" alt="MQT Partner Logos">
  </picture>
</p>

Thank you to all the contributors who have helped make MQT SQR a reality!

<p align="center">
  <a href="https://github.com/munich-quantum-toolkit/sqr/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=munich-quantum-toolkit/sqr" alt="Contributors to munich-quantum-toolkit/sqr" />
  </a>
</p>

The MQT will remain free, open-source, and permissively licensed—now and in the
future. We are firmly committed to keeping it open and actively maintained for
the quantum computing community.

To support this endeavor, please consider:

- Starring and sharing our repositories:
  <https://github.com/munich-quantum-toolkit>
- Contributing code, documentation, tests, or examples via issues and pull
  requests
- Citing the MQT in your publications (see [Cite This](#cite-this))
- Citing our research in your publications (see
  [References](https://mqt.readthedocs.io/projects/sqr/en/latest/references.html))
- Using the MQT in research and teaching, and sharing feedback and use cases
- Sponsoring us on GitHub: <https://github.com/sponsors/munich-quantum-toolkit>

<p align="center">
  <a href="https://github.com/sponsors/munich-quantum-toolkit">
  <img width=20% src="https://img.shields.io/badge/Sponsor-white?style=for-the-badge&logo=githubsponsors&labelColor=black&color=blue" alt="Sponsor the MQT" />
  </a>
</p>

## Getting Started

> [!NOTE]
> MQT SQR is still in active development.

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

**Detailed documentation and examples are available at
[ReadTheDocs](https://mqt.readthedocs.io/projects/sqr).**

## System Requirements

MQT SQR can be installed on all major operating systems with all supported
Python versions. Building (and running) is continuously tested under Linux,
macOS, and Windows using the
[latest available system versions for GitHub Actions](https://github.com/actions/runner-images).

## Cite This

Please cite the work that best fits your use case.

### MQT SQR (the tool)

When citing the software itself or results produced with it, cite the MQT SQR
paper:

```bibtex
@article{shen2026sqr,
  title        = {Routing Techniques for Error-Corrected Silicon Spin Qubit Quantum Architectures},
  author       = {Shen, Julian and Schmid, Ludwig and Wille, Robert},
  year         = {2026},
  eprint       = {2607.07822},
  eprinttype   = {arxiv}
}
```

### The Munich Quantum Toolkit (the project)

When discussing the overall MQT project or its ecosystem, cite the MQT Handbook:

```bibtex
@inproceedings{mqt,
  title        = {The {{MQT}} Handbook: {{A}} Summary of Design Automation Tools and Software for Quantum Computing},
  shorttitle   = {{The MQT Handbook}},
  author       = {Wille, Robert and Berent, Lucas and Forster, Tobias and Kunasaikaran, Jagatheesan and Mato, Kevin and Peham, Tom and Quetschlich, Nils and Rovara, Damian and Sander, Aaron and Schmid, Ludwig and Schoenberger, Daniel and Stade, Yannick and Burgholzer, Lukas},
  year         = 2024,
  booktitle    = {IEEE International Conference on Quantum Software (QSW)},
  doi          = {10.1109/QSW62656.2024.00013},
  eprint       = {2405.17543},
  eprinttype   = {arxiv},
  addendum     = {A live version of this document is available at \url{https://mqt.readthedocs.io}}
}
```

---

## Acknowledgements

The Munich Quantum Toolkit has been supported by the European Research Council
(ERC) under the European Union's Horizon 2020 research and innovation program
(grant agreement No. 101001318), the Bavarian State Ministry for Science and
Arts through the Distinguished Professorship Program, as well as the Munich
Quantum Valley, which is supported by the Bavarian state government with funds
from the Hightech Agenda Bayern Plus.

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/munich-quantum-toolkit/.github/refs/heads/main/docs/_static/mqt-funding-footer-dark.svg" width="90%">
    <img src="https://raw.githubusercontent.com/munich-quantum-toolkit/.github/refs/heads/main/docs/_static/mqt-funding-footer-light.svg" width="90%" alt="MQT Funding Footer">
  </picture>
</p>
