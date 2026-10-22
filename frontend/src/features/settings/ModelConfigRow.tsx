import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { ApiError } from "../../api/client";
import { updateAgentConfig, type AgentConfig, type ModelOption } from "../../api/agentConfig";
import { Button } from "../../design/Button";
import { Field, SelectInput, TextInput } from "../../design/Field";
import { BUDGETS, EFFORTS, ROLE_INFO } from "./roles";

export function ModelConfigRow({ config, models }: { config: AgentConfig; models: ModelOption[] }) {
  const queryClient = useQueryClient();
  const info = ROLE_INFO[config.agent_role] ?? { name: config.agent_role, does: "" };
  const budgets = BUDGETS[config.agent_role] ?? [];
  const [model, setModel] = useState(config.model);
  const [effort, setEffort] = useState(config.effort);
  const [params, setParams] = useState<Record<string, string>>(
    Object.fromEntries(budgets.map((b) => [b.key, String(config.params[b.key] ?? "")])),
  );

  const parsed = Object.fromEntries(budgets.map((b) => [b.key, Number(params[b.key])]));
  const badBudget = budgets.find((b) => !Number.isInteger(parsed[b.key]) || parsed[b.key] <= 0);
  const dirty =
    model !== config.model ||
    effort !== config.effort ||
    budgets.some((b) => parsed[b.key] !== config.params[b.key]);

  const save = useMutation({
    mutationFn: () => updateAgentConfig(config.agent_role, { model: model.trim(), effort, params: { ...config.params, ...parsed } }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["agent-configs"] }),
  });

  return (
    <li className="px-5 py-4">
      <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-3">
        <div className="min-w-[14rem] flex-1">
          <p className="font-medium">{info.name}</p>
          <p className="text-sm text-muted">{info.does}</p>
          <p className="mt-0.5 font-mono text-[11px] text-faint">{config.agent_role}</p>
        </div>
        <div className="flex flex-wrap items-end gap-3">
          <Field label="Model">
            {(c) => (
              <SelectInput {...c} value={model} onChange={(e) => setModel(e.target.value)} className="w-52">
                {/* A value saved earlier that is no longer offered stays selectable so nothing changes silently. */}
                {models.some((m) => m.id === model) ? null : <option value={model}>{model} (not in the list)</option>}
                <optgroup label="Pinned versions">
                  {models.filter((m) => m.group === "pinned").map((m) => (
                    <option key={m.id} value={m.id}>{m.label}</option>
                  ))}
                </optgroup>
                <optgroup label="Always the latest">
                  {models.filter((m) => m.group === "latest").map((m) => (
                    <option key={m.id} value={m.id}>{m.label}</option>
                  ))}
                </optgroup>
              </SelectInput>
            )}
          </Field>
          <Field label="Effort">
            {(c) => (
              <SelectInput {...c} value={effort} onChange={(e) => setEffort(e.target.value)} className="w-28">
                {EFFORTS.map((x) => (
                  <option key={x}>{x}</option>
                ))}
              </SelectInput>
            )}
          </Field>
        </div>
      </div>
      {budgets.length > 0 ? (
        <div className="mt-3 flex flex-wrap gap-3">
          {budgets.map((b) => (
            <Field key={b.key} label={b.label} hint={b.hint}>
              {(c) => (
                <TextInput {...c} inputMode="numeric" value={params[b.key]} onChange={(e) => setParams({ ...params, [b.key]: e.target.value })} className="w-36" />
              )}
            </Field>
          ))}
        </div>
      ) : null}
      {dirty || save.isError || save.isSuccess ? (
        <div className="mt-3 flex items-center gap-3">
          {dirty ? (
            <>
              <Button variant="primary" size="sm" loading={save.isPending} disabled={Boolean(badBudget)} onClick={() => save.mutate()}>
                Save
              </Button>
              {badBudget ? <span className="text-[13px] text-danger">{badBudget.label} must be a whole number above zero.</span> : null}
            </>
          ) : save.isSuccess ? (
            <span className="text-[13px] text-ok" role="status">Saved. New jobs use this from now on.</span>
          ) : null}
          {save.isError ? (
            <span className="text-[13px] text-danger" role="alert">
              {save.error instanceof ApiError ? save.error.message : "Could not reach the backend."}
            </span>
          ) : null}
        </div>
      ) : null}
    </li>
  );
}
