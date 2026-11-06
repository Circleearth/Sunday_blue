# Upstream components

- LivingMemory 2.9.1, commit `1c6a471c9af9ae45a4ccb3a8cec5695c917de50b`:
  https://github.com/lxfight-s-Astrbot-Plugins/astrbot_plugin_livingmemory
  Original core, storage, pages, assets, metadata and schema are in `vendor/livingmemory`.
  License: GNU AGPL-3.0, complete original text at `vendor/livingmemory/LICENSE`.
- AstrBot vector storage, tokenizer and stopwords: https://github.com/AstrBotDevs/AstrBot
  Snapshot of the locally installed source, 2026-11-06. Only required vector-storage files
  are included at `vendor/astrbot`, together with its original AGPL-3.0 LICENSE.
  File-level SHA-256 provenance is recorded in `upstream-lock.json`.
- Python package dependencies retain their own notices in the isolated environment.
- Ollama is an independent user-installed/copied runtime, not part of this source snapshot:
  https://github.com/ollama/ollama . Keep the distribution's component notices when redistributing.

The Sunday Blue adapter is outside `vendor`. No AstrBot plugin main/event bus is emulated.
Do not describe this as general AstrBot plugin compatibility. Preserve upstream licenses
and corresponding-source obligations when distributing this integration.
