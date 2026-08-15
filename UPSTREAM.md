# Upstream baseline

This repository was bootstrapped from
[`aws-samples/sample-host-hermesagent-on-amazon-bedrock-agentcore`](https://github.com/aws-samples/sample-host-hermesagent-on-amazon-bedrock-agentcore).

- Upstream revision: `b9988e3ceaacf57da4305c7f8f32cedc3e3d80ce`
- Upstream branch at selection time: `main`
- Import date: `2026-08-15`
- Import strategy: tracked-file snapshot; this repository does not pull upstream code at build time

## Intentional path mappings and exclusions

- Upstream `LICENSE` is preserved as `THIRD_PARTY_LICENSES/aws-sample-MIT-0.txt`; the root `LICENSE` remains this project's MIT license.
- Upstream `README.md` is preserved as `docs/upstream/AWS_SAMPLE_README.md`; the root `README.md` describes this product.
- Upstream `README_ZH.md` and `docs/*` are preserved under `docs/upstream/`.
- Upstream `.claude/settings.json` is excluded because it contains paths and a webhook URL specific to another environment; this repository uses its own `AGENTS.md` configuration.
- `agentcore/cdk/package.json` pins `@aws/agentcore-cdk` to the upstream-selected `0.1.0-alpha.1` release so a future npm publication cannot silently introduce an incompatible peer dependency.
- `agentcore/cdk/package.json` uses `aws-cdk-lib` `2.265.0` instead of the upstream `2.248.0` to include the current CDK security fixes while remaining compatible with the pinned AgentCore CDK release.

Future upstream updates must record the old and new revisions and review local adaptations before copying files.
