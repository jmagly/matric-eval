# Adversarial evaluation for OBLITERATUS-derived models

The publisher model card's refusal-rate and manual-substance claims are useful
source assertions, but a defensible evaluation should preserve more than a
single binary refusal score. The pinned model lineage receipt is
[obliteratus-qwen38-publisher-lineage-2026-09-09.json](obliteratus-qwen38-publisher-lineage-2026-09-09.json).

Use separate, non-interchangeable axes:

- **Safeguard violation:** whether the response supplies prohibited assistance
  under an explicit policy and threat model.
- **Refusal and over-refusal:** whether harmful requests are refused and benign
  contrasts remain answerable. Refusal alone does not establish safety or
  correctness.
- **Informativeness and truthfulness:** whether a non-refusal contains actionable
  substance and whether its claims are supported. A vacuous answer and a
  confidently false answer should not both count as successful compliance.
- **Capability retention:** evaluate general and task-specific capabilities on
  material that is not reused for direction extraction. Report category-level
  changes rather than only an aggregate score.
- **Attack robustness:** bind the attack artifact, target model, chat template,
  generation configuration, threat model, and judge. Keep direct harmful
  behaviors separate from adversarially transformed prompts.

Recommended primary references:

- [JailbreakBench](https://arxiv.org/abs/2404.01318) defines a reproducible threat
  model, 100-behavior set, attack artifacts, system/chat-template controls, and
  standardized scoring.
- [HarmBench](https://arxiv.org/abs/2402.04249) supplies a broader behavior
  taxonomy and standardized red-teaming/evaluation framework. Preserve its
  functional and semantic categories and the provenance of classifier labels.
- [Rethinking How to Evaluate Language Model Jailbreak](https://arxiv.org/abs/2404.06407)
  separates safeguard violation, informativeness, and relative truthfulness,
  addressing failures hidden by binary attack-success rates.
- [WildTeaming/WildJailbreak](https://arxiv.org/abs/2406.18510) contributes
  in-the-wild tactics and paired vanilla/adversarial forms. Its semantic
  `data_type` labels and gated access terms remain authoritative.

For issue #114, these are method references only. They do not revise the frozen
seed, item allocation, judge panel, or scale gates. Any new axis or source needs
a versioned protocol amendment before model outputs are inspected.
