import { useEffect, useState } from 'react';
import { journalApi } from '../api/workflow';

const PROMPTS = [
  'Trade Thesis',
  'Why I Entered',
  'Why I Exited',
  'What Went Well',
  'What I Would Change',
  'Additional Notes',
];

export function TradeJournal({ tradeId }: { tradeId: number }) {
  const [entry, setEntry] = useState<Record<string, unknown> | null>(null);
  const [atts, setAtts] = useState<Record<string, unknown>[]>([]);
  const [body, setBody] = useState('');
  const [followed, setFollowed] = useState('NOT_ASSESSED');
  const [prompts, setPrompts] = useState<Record<string, string>>({});
  const [tags, setTags] = useState('');
  const [viewer, setViewer] = useState<Record<string, unknown> | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  const load = () => {
    journalApi.trade(tradeId).then((d) => {
      const e = (d.entry || null) as Record<string, unknown> | null;
      setEntry(e);
      setAtts((d.attachments as Record<string, unknown>[]) || []);
      setBody(String(e?.body || ''));
      setFollowed(String(e?.followed_plan || 'NOT_ASSESSED'));
      setPrompts((e?.prompt_fields as Record<string, string>) || {});
      setTags(((e?.tags as string[]) || []).join(', '));
    });
  };

  useEffect(() => {
    load();
  }, [tradeId]);

  const save = async () => {
    await journalApi.saveTrade(tradeId, {
      body,
      followed_plan: followed,
      prompt_fields: prompts,
      tags: tags.split(',').map((t) => t.trim()).filter(Boolean),
    });
    setMsg('Journal saved.');
    load();
  };

  const onFiles = async (files: FileList | null) => {
    if (!files) return;
    for (const f of Array.from(files)) {
      await journalApi.upload(f, tradeId);
    }
    load();
  };

  const onPaste = async (e: React.ClipboardEvent) => {
    const items = e.clipboardData?.items;
    if (!items) return;
    for (const item of Array.from(items)) {
      if (item.type.startsWith('image/')) {
        const file = item.getAsFile();
        if (file) await journalApi.upload(file, tradeId, 'Pasted screenshot');
      }
    }
    load();
  };

  return (
    <div className="card" style={{ marginTop: '1.5rem' }} onPaste={onPaste}>
      <h3>JOURNAL</h3>
      <p className="text-secondary">Subjective notes only. Not compliance scoring. Screenshots stay on this machine.</p>
      {PROMPTS.map((label) => (
        <label key={label} style={{ display: 'block', marginBottom: '0.5rem' }}>
          {label}
          <textarea
            value={prompts[label] || ''}
            onChange={(e) => setPrompts({ ...prompts, [label]: e.target.value })}
            rows={2}
            style={{ width: '100%' }}
          />
        </label>
      ))}
      <label>
        Followed my plan?
        <select value={followed} onChange={(e) => setFollowed(e.target.value)}>
          <option>NOT_ASSESSED</option>
          <option>YES</option>
          <option>NO</option>
          <option>PARTIAL</option>
        </select>
      </label>
      <label style={{ display: 'block', marginTop: '0.5rem' }}>
        Tags (comma-separated)
        <input value={tags} onChange={(e) => setTags(e.target.value)} placeholder="FOMO, PATIENT, NEWS" style={{ width: '100%' }} />
      </label>
      <label style={{ display: 'block', marginTop: '0.5rem' }}>
        Additional notes
        <textarea value={body} onChange={(e) => setBody(e.target.value)} rows={3} style={{ width: '100%' }} />
      </label>
      <button type="button" className="primary" onClick={save} style={{ marginTop: '0.5rem' }}>
        Save journal
      </button>
      {msg && <p>{msg}</p>}
      {entry && <p className="text-secondary">Updated {String(entry.updated_at || '')}</p>}

      <h4>Screenshots</h4>
      <input type="file" accept="image/png,image/jpeg,image/webp" multiple onChange={(e) => onFiles(e.target.files)} />
      <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', marginTop: '0.75rem' }}>
        {atts.map((a) => (
          <button key={String(a.id)} type="button" onClick={() => setViewer(a)} style={{ padding: 0, border: '1px solid var(--border)' }}>
            <img src={String(a.url)} alt={String(a.caption || a.original_filename)} width={96} height={72} style={{ objectFit: 'cover' }} />
          </button>
        ))}
      </div>
      {viewer && (
        <div className="card" style={{ marginTop: '0.75rem' }}>
          <img src={String(viewer.url)} alt="" style={{ maxWidth: '100%' }} />
          <input
            value={String(viewer.caption || '')}
            onChange={(e) => setViewer({ ...viewer, caption: e.target.value })}
            placeholder="Caption"
          />
          <button type="button" onClick={() => journalApi.caption(Number(viewer.id), String(viewer.caption || '')).then(load)}>
            Save caption
          </button>
          <button
            type="button"
            onClick={() => {
              if (window.confirm('Delete this screenshot?')) {
                journalApi.remove(Number(viewer.id)).then(() => {
                  setViewer(null);
                  load();
                });
              }
            }}
          >
            Delete
          </button>
          <button type="button" onClick={() => setViewer(null)}>
            Close
          </button>
        </div>
      )}
    </div>
  );
}
