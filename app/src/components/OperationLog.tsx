import { useTranslation } from "react-i18next";
import { useEffect, useId, useRef, useState } from "react";

export function OperationLog({ logs, finished, training }: { logs: string; finished: boolean; training: boolean }) {
  const { t } = useTranslation();
  const titleId = useId();
  const viewport = useRef<HTMLPreElement>(null);
  const [follow, setFollow] = useState(true);
  useEffect(() => {
    if (follow && viewport.current) viewport.current.scrollTop = viewport.current.scrollHeight;
  }, [logs, follow]);

  return <section className="mt-6 min-w-0" aria-labelledby={titleId}>
    <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
      <div>
        <h2 id={titleId} className="text-lg font-semibold">{t(training ? "trainingLogs" : "operationLogs")}</h2>
        <p className="text-sm opacity-70">{t("recentOutput")} · {t(finished ? "runFinished" : "updatesAutomatically")}</p>
      </div>
      <label className="flex cursor-pointer items-center gap-2 text-sm">
        <input type="checkbox" className="checkbox checkbox-sm" checked={follow}
          onChange={event => setFollow(event.target.checked)} />
        {t("followOutput")}
      </label>
    </div>
    <pre ref={viewport} tabIndex={0} aria-label={t(training ? "trainingLogOutput" : "operationLogOutput")}
      onScroll={event => {
        const element = event.currentTarget;
        setFollow(element.scrollHeight - element.scrollTop - element.clientHeight < 32);
      }}
      className="h-80 overflow-auto rounded-xl bg-slate-950 p-5 font-mono text-sm leading-relaxed text-slate-200 whitespace-pre-wrap break-words focus:outline-none focus:ring-2 focus:ring-primary">
      {logs || t(finished ? "noContainerOutput" : training ? "waitingTrainingOutput" : "waitingOperationOutput")}
    </pre>
    {logs && <p className="mt-2 text-sm opacity-70">{t("originalLogsNote")}</p>}
  </section>;
}
