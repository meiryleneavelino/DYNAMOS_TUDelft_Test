import { useMemo, useState } from "react";
import { CheckCircle2, Clock, XCircle, Boxes, ShieldCheck } from "lucide-react";
import StatCard from "@/components/StatCard";
import Panel from "@/components/Panel";
import JobsTable from "@/components/JobsTable";
import SandboxStatusPanel from "@/components/SandboxStatusPanel";
import AuthorizationsPanel from "@/components/AuthorizationsPanel";
import LedgerTimeline from "@/components/LedgerTimeline";
import UsageChart from "@/components/charts/UsageChart";
import ModelDistributionChart from "@/components/charts/ModelDistributionChart";
import {
  mockJobs,
  mockAuthorizations,
  mockLedgerEvents,
  mockSandboxStatus,
  mockModelUsage,
  mockResourceUsage,
} from "@/data/mock";
import type { JobStatus } from "@/types";

type Filter = "all" | JobStatus;

export default function Dashboard() {
  const [filter, setFilter] = useState<Filter>("all");

  const visibleJobs = useMemo(
    () => (filter === "all" ? mockJobs : mockJobs.filter((j) => j.status === filter)),
    [filter]
  );

  const counts = useMemo(
    () => ({
      authorized: mockJobs.filter((j) => j.status === "authorized" || j.status === "done").length,
      running: mockJobs.filter((j) => j.status === "running").length,
      denied: mockJobs.filter((j) => j.status === "denied").length,
      released: mockJobs.filter((j) => j.status === "done").length,
    }),
    []
  );

  return (
    <>
      <div className="mb-5.5 flex items-center justify-between gap-5 rounded-card bg-gradient-to-r from-navy-900 to-navy-700 px-6.5 py-5.5 text-[#f1f0fa]">
        <div>
          <h2 className="m-0 mb-1 font-serif text-[22px] font-semibold">Welcome, Meirylene 👋</h2>
          <p className="m-0 max-w-[520px] text-[13px] leading-relaxed text-[#c3c3de]">
            Here you can request authorizations, submit training jobs, track
            progress, and view the event history of your research.
          </p>
        </div>
        <div className="flex flex-none items-center gap-2.5 whitespace-nowrap rounded-[11px] border border-white/[0.14] bg-white/[0.07] px-4 py-2.5 text-xs text-[#e2e0f5]">
          <ShieldCheck size={20} className="flex-none text-gold" />
          <span>
            Responsible research. Protected data.
            <br />
            Results that make a difference.
          </span>
        </div>
      </div>

      <div className="mb-5.5 grid grid-cols-4 gap-3.5">
        <StatCard
          title="Authorized jobs"
          value={counts.authorized}
          footnote="Last 30 days"
          icon={<CheckCircle2 size={15} className="text-status-green" />}
          iconBg="#e4f7ee"
          selected={filter === "authorized"}
          onClick={() => setFilter(filter === "authorized" ? "all" : "authorized")}
        />
        <StatCard
          title="Jobs in progress"
          value={counts.running}
          footnote="Currently active"
          icon={<Clock size={15} className="text-status-blue" />}
          iconBg="#e8eefb"
          selected={filter === "running"}
          onClick={() => setFilter(filter === "running" ? "all" : "running")}
        />
        <StatCard
          title="Denied jobs"
          value={counts.denied}
          footnote="Last 30 days"
          icon={<XCircle size={15} className="text-status-red" />}
          iconBg="#fbe9e8"
          selected={filter === "denied"}
          onClick={() => setFilter(filter === "denied" ? "all" : "denied")}
        />
        <StatCard
          title="Released models"
          value={counts.released}
          footnote="Ready to use"
          icon={<Boxes size={15} className="text-violet-deep" />}
          iconBg="#ece9fb"
          selected={filter === "done"}
          onClick={() => setFilter(filter === "done" ? "all" : "done")}
        />
      </div>

      <div className="grid grid-cols-[1.65fr_1fr] items-start gap-4.5">
        <div>
          <Panel
            title="Your recent jobs"
            right={
              <a href="/jobs" className="text-xs font-bold text-violet-deep">
                View all →
              </a>
            }
          >
            <JobsTable jobs={visibleJobs} />
          </Panel>

          <div className="grid grid-cols-[1.5fr_1fr] gap-4.5">
            <Panel title="Resource usage (last 7 days)">
              <UsageChart data={mockResourceUsage} />
            </Panel>
            <Panel title="Most used model">
              <ModelDistributionChart data={mockModelUsage} />
            </Panel>
          </div>
        </div>

        <div>
          <SandboxStatusPanel items={mockSandboxStatus} />
          <AuthorizationsPanel authorizations={mockAuthorizations} />
          <LedgerTimeline events={mockLedgerEvents} />
        </div>
      </div>
    </>
  );
}
