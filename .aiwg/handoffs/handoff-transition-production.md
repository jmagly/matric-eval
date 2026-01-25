# Handoff Checklist: Transition → Production

**Project**: matric-eval
**Phase Transition**: Transition → Production (Support Teams)
**Date**: _____________
**Purpose**: Verify production readiness, support infrastructure, and operations handoff

---

## 1. Release Notes Published

### 1.1 Release Announcement
- [ ] **Release version** finalized (e.g., v1.0.0)
- [ ] **Release date** set
- [ ] **Release notes** published:
  - [ ] Summary of new features
  - [ ] Breaking changes highlighted
  - [ ] Migration guide from previous versions
  - [ ] Known issues and workarounds
  - [ ] Contributors acknowledged
- [ ] **Communication channels** notified:
  - [ ] matric-cli team (Slack/email)
  - [ ] matric-memory team (Slack/email)
  - [ ] DevOps team (Slack/email)
  - [ ] Project mailing list (if applicable)
  - [ ] Gitea release page published

### 1.2 Version Artifacts Published
- [ ] **Python package** (PyPI or internal registry):
  - [ ] `matric-eval==1.0.0` installable via `uv pip install matric-eval`
  - [ ] Package metadata correct (description, license, homepage)
  - [ ] Changelog link in package description
- [ ] **TypeScript binding** (npm):
  - [ ] `@matric/eval@1.0.0` installable via `npm install @matric/eval`
  - [ ] Package README links to documentation
- [ ] **Rust binding** (crates.io):
  - [ ] `matric-eval@1.0.0` addable via `cargo add matric-eval`
  - [ ] Docs.rs documentation auto-generated
- [ ] **Git tags** created and pushed:
  - [ ] `v1.0.0` tag on main branch
  - [ ] Tag signed (GPG) if policy requires

### 1.3 Documentation Published
- [ ] **Official documentation site** live (if applicable):
  - [ ] Hosted at docs.matric.dev/eval or similar
  - [ ] Versioned docs (v1.0.0 viewable)
- [ ] **README.md** links to:
  - [ ] Documentation site
  - [ ] Release notes
  - [ ] Issue tracker
  - [ ] Support channels
- [ ] **CHANGELOG.md** updated with v1.0.0 entry

---

## 2. Support Documentation Ready

### 2.1 User Support Materials
- [ ] **FAQ document** created:
  - [ ] Common installation issues (uv not found, Docker not running)
  - [ ] Common runtime errors (Ollama connection refused, model not found)
  - [ ] Configuration questions (seed, tier selection, timeouts)
  - [ ] Performance optimization (model filtering, parallel execution)
- [ ] **Troubleshooting guide**:
  - [ ] Log file locations (`~/.matric-eval/logs/`)
  - [ ] Verbose mode (`--verbose` flag)
  - [ ] State file inspection (meta.json, state.json)
  - [ ] Common error codes and meanings
- [ ] **Video tutorials** (optional but recommended):
  - [ ] Quick start (5-minute eval)
  - [ ] Checkpoint/resume walkthrough
  - [ ] Custom test creation

### 2.2 Operations Runbooks
- [ ] **Installation runbook**:
  - [ ] Prerequisites checklist (Python, uv, Docker, Ollama)
  - [ ] Step-by-step installation (Linux, macOS, Windows if supported)
  - [ ] Verification steps (run smoke test)
  - [ ] Rollback procedure (uninstall, revert)
- [ ] **Configuration runbook**:
  - [ ] Environment variables reference
  - [ ] Config file examples (tiers, model filters)
  - [ ] Ollama setup and tuning
  - [ ] Docker sandbox configuration
- [ ] **Backup/restore runbook**:
  - [ ] Results directory backup (tar/rsync)
  - [ ] State file importance (meta.json, state.json)
  - [ ] Restore procedure (copy back, resume)
- [ ] **Upgrade runbook**:
  - [ ] Pre-upgrade checklist (backup results, note version)
  - [ ] Upgrade steps (`uv pip install --upgrade matric-eval`)
  - [ ] Post-upgrade validation (run smoke test)
  - [ ] Rollback procedure (downgrade version)

### 2.3 Developer Support Materials
- [ ] **API reference** published:
  - [ ] Python API docs (Sphinx or MkDocs)
  - [ ] TypeScript binding API (TSDoc)
  - [ ] Rust binding API (docs.rs)
- [ ] **Integration examples**:
  - [ ] matric-cli integration example (TypeScript)
  - [ ] matric-memory integration example (Rust)
  - [ ] CI/CD pipeline example (GitHub Actions)
  - [ ] Custom task example (JSONL + scorer)
- [ ] **Extension guide**:
  - [ ] Adding new public benchmarks
  - [ ] Creating custom scorers
  - [ ] Implementing new solvers

---

## 3. Monitoring Configured

### 3.1 Health Checks
- [ ] **CLI health check** command:
  - [ ] `matric-eval --health` verifies:
    - [ ] Ollama reachable
    - [ ] Docker available
    - [ ] Datasets accessible
    - [ ] Write permissions for results directory
- [ ] **Automated health monitoring** (if applicable):
  - [ ] Cron job or systemd timer runs health check
  - [ ] Alerts on health check failure

### 3.2 Logging Infrastructure
- [ ] **Logging configured**:
  - [ ] Log files written to `~/.matric-eval/logs/` or configurable location
  - [ ] Log rotation enabled (max 10 files, 10MB each)
  - [ ] Log levels configurable (DEBUG, INFO, WARNING, ERROR)
  - [ ] Structured logging (JSON format for machine parsing)
- [ ] **Log aggregation** (if centralized logging available):
  - [ ] Logs forwarded to Splunk/ELK/Grafana Loki
  - [ ] Dashboards created for eval metrics

### 3.3 Metrics Collection
- [ ] **Performance metrics** tracked:
  - [ ] Eval run duration (per tier, per model)
  - [ ] Problem completion rate
  - [ ] Error rate by type (network, timeout, validation)
  - [ ] Resource usage (CPU, memory, disk)
- [ ] **Business metrics** tracked:
  - [ ] Number of evals run per day/week
  - [ ] Top evaluated models
  - [ ] Most used benchmarks
  - [ ] Config recommendation adoption rate
- [ ] **Metrics dashboard** (optional):
  - [ ] Grafana dashboard for matric-eval metrics
  - [ ] Prometheus exporters (if applicable)

### 3.4 Error Tracking
- [ ] **Error reporting** mechanism:
  - [ ] Sentry/Rollbar integration (optional)
  - [ ] Crash dumps collected (state files on error)
  - [ ] Error logs include context (model, benchmark, problem_id)
- [ ] **Alert thresholds** defined:
  - [ ] >10% error rate triggers alert
  - [ ] Eval run >4 hours triggers warning
  - [ ] Disk usage >90% triggers alert

---

## 4. Escalation Paths Defined

### 4.1 Support Tiers
- [ ] **L1 Support** (User self-service):
  - [ ] FAQ and troubleshooting docs
  - [ ] Community forum or Slack channel
  - [ ] GitHub/Gitea issue templates
- [ ] **L2 Support** (Operations team):
  - [ ] Email: matric-eval-support@example.com
  - [ ] Response SLA: 1 business day
  - [ ] Handles: installation issues, config questions, basic debugging
- [ ] **L3 Support** (Development team):
  - [ ] Email: matric-dev-team@example.com
  - [ ] Response SLA: 2 business days
  - [ ] Handles: bugs, feature requests, deep debugging

### 4.2 Issue Classification
- [ ] **Severity levels** defined:
  - [ ] **P0 (Critical)**: Eval crashes, data loss, security issue
    - Response: 4 hours
    - Resolution: 1 business day
  - [ ] **P1 (High)**: Major functionality broken, no workaround
    - Response: 1 business day
    - Resolution: 1 week
  - [ ] **P2 (Medium)**: Minor functionality broken, workaround exists
    - Response: 3 business days
    - Resolution: Next release
  - [ ] **P3 (Low)**: Enhancement request, cosmetic issue
    - Response: Best effort
    - Resolution: Future release
- [ ] **Issue triage process** documented:
  - [ ] User creates issue with template
  - [ ] L2 support triages within 1 business day
  - [ ] Assigns severity and routes to L3 if needed

### 4.3 Escalation Contacts
- [ ] **Primary contact** (Development Team Lead):
  - Name: _____________
  - Email: _____________
  - Slack: _____________
  - Availability: Business hours (Mon-Fri 9am-5pm)
- [ ] **Secondary contact** (Senior Developer):
  - Name: _____________
  - Email: _____________
  - Slack: _____________
  - Availability: Business hours (Mon-Fri 9am-5pm)
- [ ] **Emergency contact** (On-call, for P0 issues):
  - Rotation schedule: _____________
  - On-call phone: _____________
  - Escalation procedure: _____________

---

## 5. Hypercare Team Assigned

### 5.1 Hypercare Period Defined
- [ ] **Hypercare duration**: 4 weeks post-release (typical)
- [ ] **Hypercare start date**: _____________
- [ ] **Hypercare end date**: _____________
- [ ] **Hypercare objectives**:
  - [ ] Monitor adoption by matric-cli and matric-memory teams
  - [ ] Respond rapidly to integration issues
  - [ ] Collect user feedback for v1.1.0 improvements
  - [ ] Validate production performance matches test environments

### 5.2 Hypercare Team Roster
- [ ] **Hypercare Lead**: _____________
  - Responsibilities: Daily standup, issue coordination, stakeholder comms
- [ ] **Developer 1**: _____________
  - Responsibilities: Bug fixes, performance tuning
- [ ] **Developer 2** (optional): _____________
  - Responsibilities: Documentation updates, user support
- [ ] **DevOps Engineer**: _____________
  - Responsibilities: CI/CD issues, infrastructure monitoring
- [ ] **QA Engineer** (optional): _____________
  - Responsibilities: Regression testing, validation

### 5.3 Hypercare Activities
- [ ] **Daily standup** (15 min):
  - Review new issues
  - Discuss blockers
  - Plan hotfixes if needed
- [ ] **Weekly retrospective**:
  - Review metrics (adoption, errors, performance)
  - Identify trends
  - Plan process improvements
- [ ] **User feedback sessions**:
  - Week 1: matric-cli team check-in
  - Week 2: matric-memory team check-in
  - Week 4: DevOps team check-in
- [ ] **Hotfix release process** defined:
  - Criteria for hotfix (P0 bug, security issue)
  - Fast-track testing and release
  - Notification procedure

### 5.4 Hypercare Success Criteria
- [ ] **Adoption metrics**:
  - [ ] matric-cli integration complete and stable
  - [ ] matric-memory integration complete and stable
  - [ ] At least 10 eval runs completed by end of week 1
- [ ] **Quality metrics**:
  - [ ] <5% error rate in production evals
  - [ ] No P0 bugs open at end of hypercare
  - [ ] User satisfaction ≥4/5 (survey)
- [ ] **Handoff to BAU** (Business as Usual) support ready:
  - [ ] Runbooks validated in production
  - [ ] L2 support trained
  - [ ] Knowledge transfer complete

---

## 6. Production Environment Validated

### 6.1 Infrastructure Readiness
- [ ] **Ollama service** production-ready:
  - [ ] Stable version deployed (pinned, not latest)
  - [ ] Sufficient GPU/CPU capacity for concurrent evals
  - [ ] Health monitoring enabled
- [ ] **Docker** available on target systems:
  - [ ] Version validated (24.x or 25.x)
  - [ ] Sandbox images pre-pulled (Python, execution environments)
- [ ] **Storage** provisioned:
  - [ ] Results directory with sufficient space (estimate: 1GB per 100 evals)
  - [ ] Dataset directory accessible (symlink to `/home/roctinam/data/evals/`)
  - [ ] Backup strategy for results (daily/weekly)
- [ ] **Network** configuration:
  - [ ] Ollama API accessible (http://localhost:11434 or configured URL)
  - [ ] Outbound internet for dataset downloads (if needed)
  - [ ] Firewall rules allow Docker networking

### 6.2 Security Validation
- [ ] **Code execution sandboxing** verified:
  - [ ] Docker containers run as non-root
  - [ ] Resource limits enforced (CPU, memory, disk)
  - [ ] Network isolation enabled (no external network access from sandbox)
- [ ] **Access controls**:
  - [ ] Results directory permissions restrictive (owner only)
  - [ ] Ollama API access controlled (localhost only or auth enabled)
- [ ] **Secrets management**:
  - [ ] No hardcoded credentials in code
  - [ ] API tokens stored securely (env vars, vault)
- [ ] **Security scan** passed:
  - [ ] Dependency vulnerability scan (uv audit or safety)
  - [ ] Container image scan (Docker Scout or Trivy)
  - [ ] SAST scan (Bandit for Python)

### 6.3 Performance Validation
- [ ] **Load testing** completed:
  - [ ] Smoke tier: <2 min (validated in production)
  - [ ] Quick tier: <20 min (validated in production)
  - [ ] Full tier: <3 hours (validated in production)
  - [ ] Concurrent runs: System handles 3+ simultaneous evals
- [ ] **Resource usage** within limits:
  - [ ] Memory: <4GB per eval process
  - [ ] Disk: <100MB per model result
  - [ ] CPU: Saturates available cores efficiently
- [ ] **Stability testing**:
  - [ ] 24-hour continuous eval run completed without crashes
  - [ ] Checkpoint/resume tested under load

### 6.4 Disaster Recovery
- [ ] **Backup strategy** implemented:
  - [ ] Results directory backed up daily
  - [ ] State files included in backups
  - [ ] Retention policy defined (90 days)
- [ ] **Restore tested**:
  - [ ] Backup restore successful
  - [ ] Eval resume from restored state works
- [ ] **Failover plan**:
  - [ ] If Ollama down: Clear error message, retry logic
  - [ ] If Docker down: Clear error message, graceful exit
  - [ ] If disk full: Warning, graceful degradation

---

## 7. Knowledge Transfer Complete

### 7.1 Operations Team Training
- [ ] **Training session 1**: Installation and configuration
  - Date: _____________
  - Attendees: _____________
  - Materials: Installation runbook, config examples
- [ ] **Training session 2**: Troubleshooting and support
  - Date: _____________
  - Attendees: _____________
  - Materials: Troubleshooting guide, log analysis
- [ ] **Training session 3**: Advanced scenarios
  - Date: _____________
  - Attendees: _____________
  - Materials: Checkpoint/resume, custom tests, CI/CD

### 7.2 Support Team Enablement
- [ ] **L2 support** trained on:
  - [ ] Common issues and resolutions
  - [ ] How to read logs and state files
  - [ ] When to escalate to L3 (dev team)
  - [ ] Issue triage process
- [ ] **L2 support** has access to:
  - [ ] Documentation repository
  - [ ] Runbooks repository
  - [ ] Issue tracker
  - [ ] Team chat channels

### 7.3 Stakeholder Readiness
- [ ] **matric-cli team** onboarded:
  - [ ] TypeScript binding usage demonstrated
  - [ ] Integration example reviewed
  - [ ] Support contact provided
- [ ] **matric-memory team** onboarded:
  - [ ] Rust binding usage demonstrated
  - [ ] Integration example reviewed
  - [ ] Support contact provided
- [ ] **DevOps team** onboarded:
  - [ ] CI/CD integration example reviewed
  - [ ] Monitoring dashboards explained
  - [ ] Escalation process understood

---

## 8. Handoff Criteria Met

**Production support handoff may occur when**:
- Release notes published and artifacts available
- Support documentation complete (FAQ, runbooks, API docs)
- Monitoring and alerting configured
- Escalation paths defined and contacts assigned
- Hypercare team assigned and ready
- Production environment validated (infra, security, performance, DR)
- Knowledge transfer complete (ops, support, stakeholders)

---

## 9. Post-Handoff Activities

### 9.1 Transition Closure
- [ ] **Transition retrospective** conducted:
  - What went well
  - What could be improved
  - Action items for next release
- [ ] **Lessons learned** documented:
  - [ ] Added to project knowledge base
  - [ ] Shared with broader team
- [ ] **Transition artifacts** archived:
  - [ ] Handoff checklists
  - [ ] Training materials
  - [ ] Runbooks and guides

### 9.2 Ongoing Operations
- [ ] **BAU support** team takes over after hypercare (Week 4):
  - [ ] L2 support handles issues independently
  - [ ] L3 escalations handled per SLA
  - [ ] Monthly metrics review with stakeholders
- [ ] **Continuous improvement**:
  - [ ] User feedback collected and triaged
  - [ ] Roadmap updated based on production learnings
  - [ ] Next release planning begins (v1.1.0)

---

**Handoff Prepared By**: Release Manager / Hypercare Lead
**Handoff Received By**: Operations Team Lead / Support Team Lead
**Handoff Date**: _____________

**Signatures**:
- [ ] Release Manager: _____________
- [ ] Hypercare Lead: _____________
- [ ] Operations Team Lead: _____________
- [ ] Support Team Lead: _____________
- [ ] Security Officer: _____________
- [ ] matric-cli Stakeholder: _____________
- [ ] matric-memory Stakeholder: _____________
- [ ] Product Owner: _____________

---

## Appendix: Contact Directory

| Role | Name | Email | Slack | Phone |
|------|------|-------|-------|-------|
| Hypercare Lead | _____________ | _____________ | _____________ | _____________ |
| Dev Team Lead | _____________ | _____________ | _____________ | _____________ |
| Operations Lead | _____________ | _____________ | _____________ | _____________ |
| Support Lead | _____________ | _____________ | _____________ | _____________ |
| Product Owner | _____________ | _____________ | _____________ | _____________ |
| Security Contact | _____________ | _____________ | _____________ | _____________ |

## Appendix: Key Resources

| Resource | Location | Access |
|----------|----------|--------|
| Source code | https://git.integrolabs.net/roctinam/matric-eval | All team members |
| Documentation | https://docs.matric.dev/eval | Public |
| Issue tracker | https://git.integrolabs.net/roctinam/matric-eval/issues | All team members |
| CI/CD | https://git.integrolabs.net/roctinam/matric-eval/actions | All team members |
| Monitoring | https://grafana.example.com/matric-eval | Ops team |
| Logs | https://splunk.example.com/matric-eval | Ops + support |
| Runbooks | https://wiki.example.com/matric-eval/runbooks | Ops + support |
