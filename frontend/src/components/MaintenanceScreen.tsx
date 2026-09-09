import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ShieldCheck, Wrench } from 'lucide-react';

function formatEnd(value: string | null | undefined) {
  return value ? new Intl.DateTimeFormat('sk-SK', { dateStyle: 'long', timeStyle: 'short' }).format(new Date(value)) : '';
}

export default function MaintenanceScreen({ endsAt }: { endsAt: string | null | undefined }) {
  const [remaining, setRemaining] = useState(() => Math.max(0, new Date(endsAt ?? 0).getTime() - Date.now()));
  useEffect(() => {
    const timer = window.setInterval(() => setRemaining(Math.max(0, new Date(endsAt ?? 0).getTime() - Date.now())), 1000);
    return () => window.clearInterval(timer);
  }, [endsAt]);
  const hours = Math.floor(remaining / 3_600_000);
  const minutes = Math.floor((remaining % 3_600_000) / 60_000);
  const seconds = Math.floor((remaining % 60_000) / 1000);
  return <main className="maintenance-screen">
    <div className="maintenance-brand"><img className="logoimg" src="/logo-zdravy-projekt.png" alt="Zdravý projekt" /></div>
    <section className="maintenance-card" aria-live="polite">
      <div className="maintenance-badge" aria-hidden="true"><Wrench /></div>
      <p className="eyebrow">Prebieha údržba</p><h1>O chvíľu sme späť</h1>
      <p className="maintenance-copy">Aplikácia je z technických príčin dočasne nedostupná.</p>
      <p className="maintenance-return">Svoje objednávky budete môcť znova zadávať:</p>
      <time className="maintenance-date">{formatEnd(endsAt)}</time>
      <div className="maintenance-countdown" aria-label={`Zostáva ${hours} hodín, ${minutes} minút a ${seconds} sekúnd`}>
        <span><b>{String(hours).padStart(2, '0')}</b>hod</span><i>:</i><span><b>{String(minutes).padStart(2, '0')}</b>min</span><i>:</i><span><b>{String(seconds).padStart(2, '0')}</b>sek</span>
      </div>
      <Link className="zp-link maintenance-admin-link" to="/admin-login"><ShieldCheck /> Prihlásenie pre administrátorov</Link>
    </section>
  </main>;
}
