---
name: marvelous-designer
description: Operate Marvelous Designer through its local MCP server for garment topology, sewing, simulation, import/export and runtime API research.
---

Use the marvelous-designer MCP server.

1. Inspect environment_info and the active scene first. Start the registered md_start_listener plugin only if unavailable. Preserve user projects; perform regression work in disposable test scenes.
2. Do not encode long-running garment-making workflows as single MCP calls. MCP tools should expose deterministic, inspectable and verifiable operations. Orchestrate complex garments incrementally: READ → PLAN → EXECUTE → VERIFY → REPLAN. Garment design and whether to continue belong to the Agent.
3. For unfamiliar APIs use search_md_docs/get_md_doc → inspect_md_api → read scene → execute → verify. Docs establish semantics; runtime confirms availability. Do not guess signatures, undocumented enums or indices. Keep API references in the docs index.
4. Prefer get_pattern_topology using a pattern UUID or unique name, then point_ref and edge_ref with move_pattern_point/create_sewing. References bind to the listener session and an exact geometry snapshot. On STALE_REFERENCE or ambiguous mapping, reread topology and replan; never choose the nearest-looking edge. Geometry edits conservatively invalidate all refs for that pattern. Import, raw execute_python and checkpoint restore invalidate the reference session.
5. Curve control points in exported JSON are not runtime endpoint indices. Outer endpoints on straight/curved boundaries are mutable; internal/control-point editing has no verified dedicated primitive. Preserve raw data. Whole outer/internal straight/curve sewing is available; partial/free ranges are unsupported. Check seam direction and length readback.
6. Create a checkpoint before risky topology/sewing/fitting changes. With no verified sewing-delete API, restore_checkpoint and recreate is the fallback. Restore replaces the scene and refreshes refs. Checkpoints use unique cached ZPRJ files; automatic cleanup keeps the newest 20 and removes older entries only after 7 days. Keep durable milestones outside this cache.
7. Low-risk, reversible and verifiable steps proceed automatically. For fitting, placement or seam corrections use a bounded loop, normally at most 4 attempts. Verify each attempt. If recovery reaches the limit, report the issue, attempts and remaining alternatives.
8. Ask the user when design intent is ambiguous, valid choices materially change the design, an irreversible decision is necessary, or bounded recovery failed. Do not ask after each small operation.
9. Record operation_id for mutations. UNKNOWN means the result is unproven, not failed. Use reconcile_operation to inspect durable completion receipts and file evidence; never automatically retry an UNKNOWN mutation. FAILED can still include partial changes; inspect or restore before replanning. Raw Python completion does not prove the intended design postcondition.
10. OBJ Avatar import is verified on MD 2026.0.315 using explicit scale, axisX/Y/Z, ImportObjectType=0 and bAdd. Use wide-character paths/getters. AVT/FBX Avatar import requires separate validation. Existing-scene replacement is guarded; use checkpoints for controlled replacement.
11. fabric_material verifies FRONT/BACK/SIDE on MD 2026.0.315. BACK/SIDE writes unlink both material and color from FRONT. assign_fabric's assign_option is a colorway option, not a face.
12. pattern_arrangement reads/writes arrangement offsets only, not arbitrary world translation or Euler angles. Do not invent rotation/placement semantics from names.
13. Simulate in small batches, inspect, then decide whether to continue. get_simulation_metrics explicitly exports garment-only OBJ snapshots and reports displacement only when connectivity, pattern IDs and reference epoch match. This is index-based measurement, not persistent vertex identity or proof of convergence/collision quality. Larger scenes need less frequent sampling.
14. The Windows SetTimer listener keeps the GUI responsive between calls. API calls stay serial on the original thread and may block during execution. Do not change this architecture or call scene APIs from workers. Avoid simultaneous manual edits/modal dialogs during mutations.
15. Prefer explicit-path imports/exports. Static modal preflight is advisory, not a sandbox. Timeouts cannot cancel MD operations. Verify geometry and fresh output contents; API success alone does not establish garment quality.

Maintenance: uv run python scripts/update_md_docs.py; --offline rebuilds cached docs. See INSTALLATION_REPORT.md for verified capabilities and current limitations.
