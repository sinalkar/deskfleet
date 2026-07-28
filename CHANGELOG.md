# Changelog

## [0.3.0](https://github.com/sinalkar/deskfleet/compare/v0.2.0...v0.3.0) (2026-07-28)


### Features

* **graph:** short-circuit out-of-scope tickets at classifier to save LLM calls ([2d7eafe](https://github.com/sinalkar/deskfleet/commit/2d7eafe1bce2d35ecf38ff61f1867d91735d5d05))
* **guardrails:** add pre-LLM out-of-scope filter and change OTHER category from ESCALATE to REFUSE ([76c95a1](https://github.com/sinalkar/deskfleet/commit/76c95a1460c81b6c02a2b1e7f0b8854cfb21bd5a))
* revamp UI as a production-grade chat console ([8c6bf2c](https://github.com/sinalkar/deskfleet/commit/8c6bf2c79a6868ff95f0adfae3fac5a87d628b4e))
* **security:** defense-in-depth prompt-hijack hardening ([eef0a7f](https://github.com/sinalkar/deskfleet/commit/eef0a7f5e7b0f5600ed8465aff4e686b57dfde4e))
* **tracing:** add LangSmith endpoint reachability probe to prevent SSL warnings ([2af2419](https://github.com/sinalkar/deskfleet/commit/2af2419445dce8700516a3a904415b9534ab8391))
* **tracing:** add manual LangSmith runs for REFUSE decisions to capture guardrail short-circuits ([647b0c6](https://github.com/sinalkar/deskfleet/commit/647b0c60256a87b0811d0262a94177f44e7d7bb8))
* **ui:** migrate to daisyUI component library and add current-date context to LLM prompts ([971f991](https://github.com/sinalkar/deskfleet/commit/971f9917e85a2b37e2b9b8093862e5c04429db4c))
* **ui:** professional product polish for the support console ([b6a8dd6](https://github.com/sinalkar/deskfleet/commit/b6a8dd6d6a84a65ca8f58d7bc19a6f7cfc028b6c))
* **ui:** soften refusal message wording for better user experience ([7751f23](https://github.com/sinalkar/deskfleet/commit/7751f23218bd7130ba5c3ac15146fd596cf1fc06))


### Bug Fixes

* /resolve 500s on injection tickets when no LLM key is configured ([d17e01b](https://github.com/sinalkar/deskfleet/commit/d17e01bd37fd9d185d731a55e0e680fea2a2b2c5))
* /resolve 500s on injection tickets when no LLM key is configured ([a8c839e](https://github.com/sinalkar/deskfleet/commit/a8c839e5b37e7e29d36ffd76e9342001352871d8))
* **ci:** correct RunTree metadata kwarg breaking mypy ([d7f2a1e](https://github.com/sinalkar/deskfleet/commit/d7f2a1ea61fd59cc8c1ca78c191c215021b066e9))
* **ci:** resolve Gitleaks and pip-audit failures on PR [#8](https://github.com/sinalkar/deskfleet/issues/8) ([bf70072](https://github.com/sinalkar/deskfleet/commit/bf70072856e502f6f4b50147db6f410b65ee2d0a))
* **ci:** resolve ruff line-length and Bandit failures on main ([e117f1c](https://github.com/sinalkar/deskfleet/commit/e117f1c36fac9157a33485df1c8b92d33ede0f2d))
* **graph:** revert OTHER category to ESCALATE and use timezone.utc for Python &lt;3.11 compatibility ([aed91fc](https://github.com/sinalkar/deskfleet/commit/aed91fce00ee9d6b1db53a91edf6e79ec1e9fdae))
* resolve CodeQL incomplete URL substring sanitization in llm.py ([94849ae](https://github.com/sinalkar/deskfleet/commit/94849ae27401c76351d3d097d567adaecd3d0b46))
* resolve CodeQL polynomial regex (ReDoS) in pii.py ([72510e8](https://github.com/sinalkar/deskfleet/commit/72510e87799d8997bd0eed07a668cbb11b4de880))
* use json_schema for local LLM structured output and increase request timeout to 300s ([b908e56](https://github.com/sinalkar/deskfleet/commit/b908e565bfcea9c95929d24b01ee5915f2e9ef1c))
