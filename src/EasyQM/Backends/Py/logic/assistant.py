# SPDX-FileCopyrightText: 2026 EasyQM contributors
# SPDX-License-Identifier: BSD-3-Clause
"""Offline assistant: canned answers from the workspace snapshot (LLM_INTEG_DESIGN.md).

Qt-free. `StubAssistant` answers when no model is configured or the user chose offline. It
reads the same `(facts, data)` snapshot the model gets (`Backends/Py/workspace.py`), so the
two stay in step.
"""

# Characters of the end of the engine output a reply may quote.
OUTPUT_QUOTE = 600


class StubAssistant:
    """Canned, context-aware answers. No network, no model."""

    name = 'Stub assistant (offline)'

    def reply(self, question: str, facts: dict, data: dict) -> str:
        asked = question.lower()
        if any(word in asked for word in ('error', 'fail', 'wrong', 'crash', 'converge')):
            return self._about_job(facts, data)
        if any(word in asked for word in ('basis', 'functional', 'method', 'level of theory', 'engine')):
            return self._about_method(facts)
        if any(word in asked for word in ('symmetry', 'point group', 'molecule', 'structure', 'atom', 'charge')):
            return self._about_sample(facts)
        if any(word in asked for word in ('result', 'energy', 'frequenc', 'summary')):
            return self._about_results(facts)
        return self._overview(facts, data)

    def suggestions(self, facts: dict) -> list[str]:
        state, page = facts['job']['state'], facts['page']
        if state == 'failed':
            return ['Why did the job fail?', 'How do I fix this error?', 'What does the output say?']
        if state == 'running':
            return ['What is the job doing now?', 'How long will this take?', 'What will I get at the end?']
        if page == 'summary' and facts['results'].get('available'):
            return ['Explain these results', 'Are these energies reasonable?', 'What should I run next?']
        if page == 'method':
            return ['Is this basis set a good choice?', 'What does the functional do?',
                    'Which engine should I use?']
        if page == 'calculations':
            return ['Which calculations do I need?', 'What is a frequency calculation for?',
                    'How long will the workflow take?']
        if page == 'sample':
            return ['What is the point group of this molecule?', 'Is the charge and multiplicity right?',
                    'How do I fix an atom?']
        return ['What is loaded right now?', 'Walk me through the workflow', 'What can you help with?']

    # Replies

    def _overview(self, facts: dict, data: dict) -> str:
        job = facts['job']
        lines = ['Here is what the workspace holds right now:', '']
        lines.append(f'- **Project:** {data.get("project_name") or "none (working without a project)"}')
        lines.append(f'- **Sample:** {_sample_line(facts["sample"])}')
        lines.append(f'- **Calculations:** {", ".join(facts["calculations"]["workflow"]) or "nothing selected yet"}')
        lines.append(f'- **Method:** {_method_line(facts["method"])}')
        lines.append(f'- **Job:** {data.get("job_message") or job["state"]}')
        lines += ['', f'You are on the *{facts["page"]}* page. '
                  'Ask about the structure, the method, the job or the results.']
        return '\n'.join(lines)

    def _about_sample(self, facts: dict) -> str:
        sample = facts['sample']
        kind = 'a periodic structure' if sample['periodic'] else 'a molecule'
        text = f'The sample is {kind}: **{sample["formula"]}** with {sample["atom_count"]} atoms. '
        if sample['point_group']:
            text += f'Its point group is **{sample["point_group"]}**. '
        text += (f'Charge {sample["charge"]}, multiplicity {sample["multiplicity"]}. '
                 'Select atoms in the viewer to measure distances, angles and dihedrals, '
                 'and tick *Fix* in the atoms table to keep an atom still during an optimisation.')
        return text

    def _about_method(self, facts: dict) -> str:
        method = facts['method']
        engine = method['engine']
        found = 'and it was found on this machine' if engine['found'] else 'but it was **not found** on this machine'
        return (f'The current engine is **{engine["name"]}**, {found}. '
                f'Level of theory: **{method.get("functional", "HF")} / {method.get("basis_set", "?")}**. '
                'A hybrid functional with a triple-zeta basis is a sound default for organic '
                'molecules; drop to double-zeta for a quick geometry pre-optimisation.')

    def _about_job(self, facts: dict, data: dict) -> str:
        state = facts['job']['state']
        if state == 'idle':
            return 'No job has run yet. Set up the calculations and the method, then press *Run workflow* on the Method page.'
        text = f'The job state is **{state}**'
        if data.get('job_message'):
            text += f': {data["job_message"]}'
        text += '.'
        tail = data.get('output_tail', '')[-OUTPUT_QUOTE:].strip()
        if tail:
            text += '\n\nThe end of the engine output reads:\n\n```\n' + tail + '\n```'
        if state == 'failed':
            text += ('\n\nUsual causes: an engine path that is wrong, a basis set the engine does not '
                     'know, or an SCF that did not converge. Check the lines above the first `ERROR`.')
        return text

    def _about_results(self, facts: dict) -> str:
        results = facts['results']
        if not results.get('available'):
            return 'There are no results yet. Run the workflow first, then open the Summary page.'
        lines = [f'Headline results of run {results["run_id"]}:', '']
        lines += [f'- {tile["title"]}: {tile["value"]}' for tile in results['tiles']]
        if not results['matches_current_state']:
            lines += ['', 'These belong to an earlier setup: ' + '; '.join(results['stale_reasons']) + '.']
        lines += ['', 'Compare energies only between runs that share the engine, functional and basis set.']
        return '\n'.join(lines)


def _sample_line(sample: dict) -> str:
    text = f'{sample["formula"]}, {sample["atom_count"]} atoms'
    return text + (f', {sample["point_group"]}' if sample['point_group'] else '')


def _method_line(method: dict) -> str:
    theory = '/'.join(value for value in (method.get('functional', ''), method.get('basis_set', '')) if value)
    return ', '.join(part for part in (method['engine']['name'], theory) if part)
