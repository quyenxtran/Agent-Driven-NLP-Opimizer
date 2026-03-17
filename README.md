# AutoResearch-SMB: AI-Driven Simulated Moving Bed Optimization

[![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)](https://python.org)
[![Pyomo](https://img.shields.io/badge/Pyomo-6.0+-orange.svg)](https://pyomo.org)
[![IPOPT](https://img.shields.io/badge/IPOPT-3.14+-green.svg)](https://coin-or.github.io/Ipopt/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**AutoResearch-SMB** is an advanced AI-driven optimization framework for Simulated Moving Bed (SMB) chromatography processes. This research-grade system combines computational chemistry, mathematical optimization, and AI agent orchestration to solve complex SMB productivity optimization problems with hard quality constraints.

## 🎯 Core Mission

Optimize SMB productivity for organic acid separation (glutaric acid and malonic acid from water/methanol feed) while satisfying stringent purity (>90%) and recovery (>90%) constraints. The framework demonstrates AI-assisted scientific discovery through a multi-agent optimization system that can outperform traditional direct MINLP approaches.

## 🧠 Knowledge Management System

AutoResearch-SMB features a comprehensive knowledge management system that captures and applies optimization expertise:

### 📚 Documentation Structure

- **[SKILLS.md](SKILLS.md)** - Durable physical intuition and proven optimization patterns
- **[HYPOTHESES.md](HYPOTHESES.md)** - Provisional beliefs requiring validation
- **[FAILURES.md](FAILURES.md)** - Systematic failure modes and recovery strategies
- **[Objectives.md](Objectives.md)** - Project goals and optimization targets
- **[LLM_SOUL.md](LLM_SOUL.md)** - AI agent operating principles and constraints

### 🤖 AI Agent Knowledge Integration

The AI agents autonomously leverage this knowledge base:

- **Scientist_A** consults SKILLS.md for proven optimization patterns when proposing candidates
- **Scientist_B** references FAILURES.md to identify potential failure modes in proposed solutions
- **Scientist_Executive** uses HYPOTHESES.md to guide experimental design and validation strategies
- **All agents** query the SQLite database for historical evidence and trend analysis

### 🔄 Continuous Learning

The system implements a continuous improvement cycle:

1. **Knowledge Application**: Agents apply documented patterns and principles
2. **Evidence Collection**: New experimental results are stored in SQLite
3. **Pattern Recognition**: Successful/unsuccessful patterns are identified
4. **Knowledge Update**: SKILLS.md, HYPOTHESES.md, and FAILURES.md are updated
5. **Validation**: New knowledge is tested in subsequent optimization cycles

## 🚀 Key Features

### 🤖 AI Agent Framework
- **Three-scientist architecture**: Scientist_A (proposer), Scientist_B (reviewer), Scientist_Executive (controller)
- **Evidence-based decision making** with SQLite-backed experiment tracking
- **LLM integration** with local Qwen3.5 9B and OpenAI fallback
- **Adversarial review process** prevents premature convergence

### 🔬 Scientific Modeling
- **Pyomo DAE-based SMB model** with discretized PDEs for chromatographic separation
- **Multi-component isotherm models** (MLL, MLLE, Langmuir) for adsorption equilibrium
- **Flexible column configuration** with variable section layouts
- **Mass transfer and transport modeling** with Peclet number and dispersion effects

### ⚡ Optimization Infrastructure
- **Multi-fidelity optimization** with automatic model refinement (low/medium/high resolution)
- **IPOPT solver integration** with multiple linear solver options (MA57, MUMPS, MA97, Pardiso)
- **Constraint-aware optimization** with hard quality requirements and pump flow limits
- **Benchmark comparison framework** against direct MINLP approaches

### 📊 Analysis & Visualization
- **Productivity vs. purity/recovery plotting**
- **3D tradeoff visualization**
- **Benchmark result summarization**
- **Performance comparison tools**

## 📋 Table of Contents

- [Installation](#installation)
- [Quick Start](#quick-start)
- [Usage Examples](#usage-examples)
- [Configuration](#configuration)
- [AI Agent Framework](#ai-agent-framework)
- [Optimization Workflow](#optimization-workflow)
- [Benchmarking](#benchmarking)
- [API Reference](#api-reference)
- [Contributing](#contributing)
- [License](#license)
- [Citation](#citation)

## 📦 Installation

### Prerequisites

- Python 3.9 or higher
- IPOPT solver (with optional linear solvers: MA57, MUMPS, MA97, Pardiso)
- Optional: CUDA-enabled GPU for local LLM inference

### Basic Installation

```bash
# Clone the repository
git clone https://github.com/your-org/AutoResearch-SMB.git
cd AutoResearch-SMB

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install core dependencies
pip install -r SembaSMB/requirement.txt

# Install optional dependencies (if IPOPT development libraries are available)
pip install -r SembaSMB/requirements-optional.txt
```

### Solver Setup

#### Option 1: Pre-built IPOPT
```bash
# Download and install IPOPT
# Add IPOPT executable to PATH
export PATH="/path/to/ipopt:$PATH"
```

#### Option 2: Build from Source
```bash
# Follow IPOPT build instructions
# Ensure linear solvers (MA57, MUMPS, etc.) are available
```

#### Option 3: Use ipopt_sens (Recommended)
```bash
# The framework defaults to ipopt_sens for sensitivity analysis
# Ensure it's available in your PATH
```

### LLM Setup (Optional)

For AI agent functionality:

```bash
# Install Ollama for local LLM inference
# https://ollama.com/

# Pull Qwen3.5 9B model
ollama pull qwen3.5:9b

# Set environment variables
export OLLAMA_BASE_URL="http://localhost:11434"
export OLLAMA_MODEL="qwen3.5:9b"
```

## 🚀 Quick Start

### 1. Basic SMB Simulation

```python
from SembaSMB.src.smb_config import SMBConfig, build_inputs
from SembaSMB.src.smb_model import build_model
from SembaSMB.src.smb_solver import solve_model

# Configure SMB parameters
config = SMBConfig(
    nc=(1, 2, 3, 2),  # Column configuration
    nfex=10,          # Extraction feed points
    nfet=5,           # Extract tank points
    ncp=2,            # Component pairs
)

# Build model inputs
inputs = build_inputs(config)

# Create Pyomo model
model = build_model(config, inputs)

# Solve optimization
results = solve_model(model, solver_name="ipopt_sens", linear_solver="ma57")

# Extract results
print(f"Productivity: {results['productivity_ex_ga_ma']}")
print(f"Purity: {results['purity_ex_meoh_free']}")
print(f"Recovery GA: {results['recovery_ex_GA']}")
print(f"Recovery MA: {results['recovery_ex_MA']}")
```

### 2. AI-Driven Optimization

```bash
# Run the full AI agent optimization
python benchmarks/agent_runner.py \
    --run-name "kraton_benchmark_001" \
    --nc-library "1,2,3,2;2,2,2,2;1,3,2,2" \
    --seed-library "notebook" \
    --benchmark-hours 12.0 \
    --search-hours 10.0 \
    --validation-hours 2.0 \
    --project-purity-min 0.90 \
    --project-recovery-ga-min 0.90 \
    --project-recovery-ma-min 0.90
```

### 3. Benchmark Comparison

```bash
# Compare AI approach vs direct MINLP
python benchmarks/agent_runner.py \
    --run-name "direct_minlp_baseline" \
    --single-scientist-mode 1 \
    --benchmark-hours 5.0 \
    --search-hours 4.0 \
    --validation-hours 1.0
```

## 📖 Usage Examples

### Example 1: Custom Optimization Problem

```python
from SembaSMB.src.smb_config import SMBConfig, FlowRates, build_inputs
from SembaSMB.src.smb_model import build_model
from SembaSMB.src.smb_optimization import add_optimization
from SembaSMB.src.smb_solver import solve_model

# Define custom flow rates
flow = FlowRates(
    F1=2.5,
    Fdes=1.5,
    Fex=1.0,
    Ffeed=1.2,
    tstep=10.0
)

# Configure SMB
config = SMBConfig(
    nc=(2, 2, 2, 2),
    L=25.0,  # Longer columns
    d=1.2,   # Larger diameter
)

# Build model
inputs = build_inputs(config, flow)
model = build_model(config, inputs)

# Add optimization constraints
model = add_optimization(
    model,
    inputs,
    purity_min=0.85,
    recovery_min_ga=0.85,
    recovery_min_ma=0.90,
    tstep_bounds=(8.0, 12.0),
    ffeed_bounds=(0.5, 2.5),
    f1_bounds=(0.5, 5.0)
)

# Solve
results = solve_model(model, solver_name="ipopt_sens", linear_solver="ma57")
```

### Example 2: Multi-Fidelity Optimization

```python
from SembaSMB.src.smb_solver import solve_model

# Low fidelity screening
config_low = SMBConfig(nfex=4, nfet=2, ncp=1)
inputs_low = build_inputs(config_low, flow)
model_low = build_model(config_low, inputs_low)
results_low = solve_model(model_low, solver_name="ipopt_sens", linear_solver="mumps")

# Medium fidelity refinement
config_med = SMBConfig(nfex=6, nfet=3, ncp=2)
inputs_med = build_inputs(config_med, flow)
model_med = build_model(config_med, inputs_med)
results_med = solve_model(model_med, solver_name="ipopt_sens", linear_solver="ma57")

# High fidelity validation
config_high = SMBConfig(nfex=10, nfet=5, ncp=2)
inputs_high = build_inputs(config_high, flow)
model_high = build_model(config_high, inputs_high)
results_high = solve_model(model_high, solver_name="ipopt_sens", linear_solver="ma57")
```

### Example 3: Custom Isotherm Model

```python
from SembaSMB.src.smb_config import SMBConfig
from SembaSMB.src.smb_isotherm import get_isotherm_params

# Use different isotherm model
config = SMBConfig(
    isoth="MLLE",  # Mixed Langmuir-Langmuir Extended
    kapp=(0.9, 1.3, 1.1, 0.7),
    qm=(0.09, 0.12, 0.025, 0.06),
    K=(260.0, 1250.0, 1e-3, 85.0),
    H=(0.65, 0.55, 1e-3, 0.07)
)
```

## ⚙️ Configuration

### SMB Configuration Parameters

```python
config = SMBConfig(
    # Column configuration
    nc=(1, 2, 3, 2),           # Columns per section (Z1, Z2, Z3, Z4)
    nfex=10,                   # Extraction feed points
    nfet=5,                    # Extract tank points
    ncp=2,                     # Component pairs
    
    # Physical parameters
    L=20.0,                    # Column length (cm)
    d=1.0,                     # Column diameter (cm)
    eb=0.44,                   # Bed porosity
    ep=0.66,                   # Particle porosity
    
    # Flow parameters (initial guesses)
    F1_init=2.2,               # SMB internal flow (mL/min)
    Fdes_init=1.2,             # Desorbent flow (mL/min)
    Fex_init=0.9,              # Extract flow (mL/min)
    Ffeed_init=1.3,            # Feed flow (mL/min)
    Fraf_init=1.6,             # Raffinate flow (mL/min)
    tstep_init=9.4,            # Switching time (min)
    
    # Chemical parameters
    comps=('GA', 'MA', 'Water', 'MeOH'),
    rho=(1.5, 1.6, 1.0, 0.79), # Densities (g/mL)
    wt0=(0.003, 0.004, 0.990, 0.003), # Feed mass fractions
    
    # Transport parameters
    kapp=(0.8, 1.22, 1.0, 0.69), # Mass transfer coefficients
    Pe=1000.0,                 # Peclet number
    
    # Isotherm parameters
    isoth='MLL',               # Isotherm type: 'MLL', 'MLLE', 'L'
)
```

### AI Agent Configuration

```bash
# Environment variables for AI agent configuration
export SMB_LLM_BASE_URL="http://localhost:11434"
export SMB_LLM_MODEL="qwen3.5:9b"
export SMB_LLM_ENABLED="1"
export SMB_FALLBACK_LLM_ENABLED="1"
export SMB_FALLBACK_LLM_BASE_URL="https://api.openai.com/v1"
export SMB_FALLBACK_LLM_MODEL="gpt-5-nano"

# Benchmark configuration
export SMB_BENCHMARK_HOURS="12.0"
export SMB_SEARCH_BUDGET_HOURS="10.0"
export SMB_VALIDATION_BUDGET_HOURS="2.0"
export SMB_MAX_SEARCH_EVALS="18"
export SMB_MAX_VALIDATIONS="3"

# Optimization constraints
export SMB_TARGET_PURITY_EX_MEOH_FREE="0.90"
export SMB_TARGET_RECOVERY_GA="0.90"
export SMB_TARGET_RECOVERY_MA="0.90"
export SMB_MAX_PUMP_FLOW_ML_MIN="2.5"
export SMB_F1_MAX_FLOW="5.0"
```

## 🤖 AI Agent Framework

### Three-Scientist Architecture

The AI framework employs three specialized agents:

#### Scientist_A (Proposer)
- **Role**: Proposes optimization hypotheses and candidate solutions
- **Responsibilities**:
  - Analyzes previous results and identifies promising regions
  - Proposes new flow rate combinations and column configurations
  - Suggests fidelity level changes based on problem difficulty
  - Generates diagnostic runs to test hypotheses

#### Scientist_B (Reviewer)
- **Role**: Independent reviewer and validator
- **Responsibilities**:
  - Verifies units, flow consistency, and fidelity choices
  - Checks solver behavior and numerical stability
  - Validates that claimed optima are actually feasible
  - Challenges proposals that lack sufficient evidence

#### Scientist_Executive (Controller)
- **Role**: Breaks optimization deadlocks and enforces policies
- **Responsibilities**:
  - Monitors consecutive rejection patterns
  - Forces execution of top-priority diagnostic runs
  - Ensures adherence to budget and time constraints
  - Maintains overall optimization strategy

### Evidence-Based Decision Making

The AI agents require concrete evidence before making decisions:

```python
# Example of evidence-based proposal
proposal = {
    "candidate_index": 3,
    "reason": "Layout (1,2,3,2) shows 15% higher productivity than (2,2,2,2)",
    "evidence": [
        "Run #12: productivity=0.018, purity=0.87, recovery=0.89",
        "Run #15: productivity=0.021, purity=0.88, recovery=0.91"
    ],
    "comparison_to_previous": [
        "vs Run #10: Δprod=+0.003, Δpurity=+0.01, Δrecovery=+0.02"
    ],
    "physics_rationale": "Zone 3 allocation improves mass transfer for GA/MA separation"
}
```

### SQLite Experiment Tracking

All experiments are tracked in a SQLite database:

```sql
-- Example query for optimization history
SELECT 
    candidate_run_name,
    nc,
    status,
    feasible,
    productivity,
    purity,
    recovery_ga,
    recovery_ma,
    normalized_total_violation
FROM simulation_results
WHERE agent_run_name = 'kraton_benchmark_001'
ORDER BY productivity DESC;
```

## 🔄 Optimization Workflow

### 1. Problem Definition
```python
# Define optimization objective
objective = "Maximize extract productivity of organic acids"
constraints = {
    "purity_ex_meoh_free": ">= 0.90",
    "recovery_ex_GA": ">= 0.90", 
    "recovery_ex_MA": ">= 0.90",
    "Ffeed": "0.5 <= Ffeed <= 2.5",
    "F1": "0.5 <= F1 <= 5.0"
}
```

### 2. Initial Screening
```python
# Low-fidelity screening across NC layouts
for nc in [(1,2,3,2), (2,2,2,2), (1,3,2,2)]:
    for seed in reference_seeds:
        run_low_fidelity_optimization(nc, seed)
```

### 3. Layout Ranking
```python
# Rank layouts by evidence
layout_scores = {
    (1,2,3,2): {"feasible": 8, "avg_productivity": 0.021, "runtime": 1200},
    (2,2,2,2): {"feasible": 5, "avg_productivity": 0.018, "runtime": 950},
    (1,3,2,2): {"feasible": 3, "avg_productivity": 0.016, "runtime": 1100}
}
```

### 4. Medium-Fidelity Refinement
```python
# Focus on top-ranked layouts
top_layouts = [(1,2,3,2), (2,2,2,2)]
for nc in top_layouts:
    for non_reference_seed in expanded_seeds:
        run_medium_fidelity_optimization(nc, seed)
```

### 5. High-Fidelity Validation
```python
# Final validation of best candidates
best_candidates = select_top_candidates(search_results, n=3)
for candidate in best_candidates:
    run_high_fidelity_validation(candidate)
```

### 6. Result Analysis
```python
# Analyze and report results
final_result = {
    "best_layout": (1,2,3,2),
    "best_flow_rates": {"F1": 2.8, "Fdes": 1.4, "Fex": 1.1, "Ffeed": 1.3, "tstep": 10.2},
    "performance": {
        "productivity": 0.0235,
        "purity": 0.912,
        "recovery_ga": 0.921,
        "recovery_ma": 0.918
    },
    "validation": "All constraints satisfied"
}
```

## 📊 Benchmarking

### Benchmark Protocol

The framework supports formal benchmarking against direct MINLP approaches:

```bash
# AI-assisted optimization benchmark
python benchmarks/agent_runner.py \
    --run-name "ai_optimization_benchmark" \
    --benchmark-hours 5.0 \
    --search-hours 4.0 \
    --validation-hours 1.0 \
    --max-search-evals 20 \
    --max-validations 5 \
    --executive-controller-enabled 1 \
    --single-scientist-mode 0

# Direct MINLP baseline
python benchmarks/agent_runner.py \
    --run-name "direct_minlp_baseline" \
    --benchmark-hours 5.0 \
    --search-hours 4.0 \
    --validation-hours 1.0 \
    --single-scientist-mode 1 \
    --max-search-evals 20
```

### Performance Metrics

```python
benchmark_metrics = {
    "primary": {
        "best_feasible_productivity": 0.0235,
        "feasibility_rate": 0.75,
        "time_to_best_solution": 3.2  # hours
    },
    "efficiency": {
        "total_solves": 45,
        "high_fidelity_solves": 8,
        "cpu_hours": 12.5,
        "wall_time": 4.8  # hours
    },
    "robustness": {
        "repeatability": 0.92,
        "solver_stability": "high",
        "constraint_violation": 0.001
    }
}
```

### Comparison Framework

```python
# Compare AI vs Direct approaches
comparison = {
    "ai_approach": {
        "productivity": 0.0235,
        "feasibility_rate": 0.75,
        "cpu_hours": 12.5,
        "wall_time": 4.8
    },
    "direct_approach": {
        "productivity": 0.0221,
        "feasibility_rate": 0.62,
        "cpu_hours": 18.2,
        "wall_time": 5.1
    },
    "improvement": {
        "productivity": "+6.3%",
        "feasibility_rate": "+21%",
        "cpu_hours": "-31%",
        "wall_time": "-6%"
    }
}
```

## 📚 API Reference

### Core Modules

#### `smb_config.py`
```python
from SembaSMB.src.smb_config import SMBConfig, FlowRates, build_inputs

# SMB configuration
config = SMBConfig(
    nc=(1, 2, 3, 2),
    nfex=10,
    nfet=5,
    ncp=2,
    # ... other parameters
)

# Flow rate definition
flow = FlowRates(
    F1=2.2,
    Fdes=1.2,
    Fex=0.9,
    Ffeed=1.3,
    tstep=9.4
)

# Build model inputs
inputs = build_inputs(config, flow)
```

#### `smb_model.py`
```python
from SembaSMB.src.smb_model import build_model

# Create Pyomo model
model = build_model(config, inputs)

# Model contains:
# - Mass balance equations
# - Equilibrium constraints
# - Flow continuity equations
# - Boundary conditions
```

#### `smb_optimization.py`
```python
from SembaSMB.src.smb_optimization import add_optimization

# Add optimization constraints
model = add_optimization(
    model,
    inputs,
    purity_min=0.85,
    recovery_min_ga=0.85,
    recovery_min_ma=0.90,
    tstep_bounds=(8.0, 12.0),
    ffeed_bounds=(0.5, 2.5),
    f1_bounds=(0.5, 5.0)
)

# Model now includes:
# - Objective function (productivity maximization)
# - Quality constraints (purity, recovery)
# - Flow bounds
# - Flow consistency constraints
```

#### `smb_solver.py`
```python
from SembaSMB.src.smb_solver import solve_model

# Solve optimization
results = solve_model(
    model,
    solver_name="ipopt_sens",
    linear_solver="ma57",
    tee=True,
    max_iter=5000,
    tol=1e-6
)

# Results include:
# - Optimized flow rates
# - Productivity metrics
# - Constraint violations
# - Solver status
```

#### `smb_metrics.py`
```python
from SembaSMB.src.smb_metrics import compute_metrics

# Compute performance metrics
metrics = compute_metrics(
    model,
    inputs,
    results,
    purity_min=0.85,
    recovery_min_ga=0.85,
    recovery_min_ma=0.90
)

# Metrics include:
# - Productivity_ex_ga_ma
# - Purity_ex_meoh_free
# - Recovery_ex_GA, Recovery_ex_MA
# - Constraint slacks
```

### Agent Runner API

```python
from benchmarks.agent_runner import main

# Run AI optimization
exit_code = main()

# Or use programmatically
from benchmarks.agent_runner import build_parser

parser = build_parser()
args = parser.parse_args([
    "--run-name", "custom_run",
    "--nc-library", "1,2,3,2;2,2,2,2",
    "--benchmark-hours", "6.0"
])

# Execute optimization
exit_code = main()
```

## 🤝 Contributing

We welcome contributions to AutoResearch-SMB! Please follow these guidelines:

### Development Setup

```bash
# Fork and clone the repository
git clone https://github.com/your-username/AutoResearch-SMB.git
cd AutoResearch-SMB

# Create development environment
python -m venv .venv-dev
source .venv-dev/bin/activate
pip install -r SembaSMB/requirement.txt
pip install -r requirements-dev.txt  # If available
```

### Code Style

- Follow PEP 8 for Python code
- Use type hints for better maintainability
- Write docstrings for all public functions
- Include unit tests for new features

### Testing

```bash
# Run tests
python -m pytest tests/

# Run specific test
python -m pytest tests/test_smb_model.py

# Run with coverage
python -m pytest --cov=SembaSMB tests/
```

### Pull Request Guidelines

1. Create a feature branch from `main`
2. Make your changes with clear commit messages
3. Add tests for new functionality
4. Update documentation as needed
5. Ensure all tests pass
6. Submit PR with a clear description

### Issue Reporting

When reporting issues, please include:

- Python version
- Operating system
- Error messages and stack traces
- Steps to reproduce
- Expected vs. actual behavior
- Any relevant configuration files

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Citation

If you use AutoResearch-SMB in your research, please cite:

```bibtex
@software{autoresearch_smb_2024,
  title={AutoResearch-SMB: AI-Driven Simulated Moving Bed Optimization},
  author={Your Name and Collaborators},
  year={2024},
  url={https://github.com/your-org/AutoResearch-SMB},
  note={Version 1.0}
}
```

## 📞 Support

For support and questions:

- **Issues**: [GitHub Issues](https://github.com/your-org/AutoResearch-SMB/issues)
- **Discussions**: [GitHub Discussions](https://github.com/your-org/AutoResearch-SMB/discussions)
- **Documentation**: [Wiki](https://github.com/your-org/AutoResearch-SMB/wiki)

## 🔗 Related Projects

- [Pyomo](https://pyomo.org/) - Python Optimization Modeling Objects
- [IPOPT](https://coin-or.github.io/Ipopt/) - Interior Point OPTimizer
- [Ollama](https://ollama.com/) - Local LLM platform
- [Qwen](https://github.com/QwenLM/Qwen) - Large language models

## 🎯 Roadmap

### Short Term (Next 3 Months)
- [ ] Add comprehensive unit tests
- [ ] Implement web-based dashboard
- [ ] Add more benchmark problems
- [ ] Improve error handling and user feedback

### Medium Term (Next 6 Months)
- [ ] Support for additional isotherm models
- [ ] Multi-objective optimization capabilities
- [ ] Uncertainty quantification tools
- [ ] Performance optimization for large-scale problems

### Long Term (Next Year)
- [ ] Integration with other chromatographic processes
- [ ] Machine learning surrogate models
- [ ] Cloud deployment support
- [ ] Commercial-grade validation and testing

---

**AutoResearch-SMB** - Where AI meets chemical engineering to solve complex optimization challenges! 🧪🤖