# Transition Phase Plan - matric-eval

**Document Type**: Phase Plan - Transition
**Project**: matric-eval - Consolidated Model Evaluation Framework
**Profile**: Production (requires full release process)
**Phase Duration**: 1 week (Week 8)
**Generated**: 2026-01-24

## Phase Overview

The Transition phase delivers matric-eval v1.0 to production. This phase focuses on deployment execution, final testing, documentation finalization, stakeholder handover, and establishing hypercare monitoring for the first 2 weeks post-release.

**Primary Goal**: Release matric-eval v1.0 to PyPI and npm with comprehensive documentation, support readiness, and monitoring in place.

**Success Definition**: By end of Week 8, matric-eval is available for installation via pip/uv and npm, integrated into matric-cli, documented for end-users, and actively monitored during hypercare period.

## Transition Strategy

### Release-Driven Approach

Week 8 is structured around the v1.0 release milestone:
- **Days 1-2**: Pre-release preparation and validation
- **Day 3**: Production deployment
- **Days 4-5**: Post-release verification and support setup
- **Weeks 9-10**: Hypercare monitoring (2 weeks post-release)

### Quality Assurance

All release criteria from Construction phase must be met before deployment. No shortcuts or deferred issues from P1-P3 scope allowed.

### Stakeholder Communication

Daily status updates to matric-cli and matric-memory teams during deployment week. Release announcement via team channels and project documentation.

## Week 8 Daily Breakdown

### Day 1 (Monday): Pre-Release Preparation

**Focus**: Final validation and release preparation

**Activities**:
- [ ] **Release Candidate Build**
  - Tag release candidate: `v1.0.0-rc.1`
  - Build Python package: `uv build`
  - Build TypeScript bindings: `npm run build`
  - Verify SBOM generation
  - Duration: 2 hours

- [ ] **Final Testing**
  - Run full test suite: `pytest --cov`
  - Verify coverage ≥80%
  - Execute smoke tests on 5 models
  - Run quick tier on 3 models
  - Validate checkpoint/resume with interruption
  - Duration: 3 hours

- [ ] **Documentation Review**
  - Review README.md completeness
  - Verify CLAUDE.md accuracy
  - Check installation instructions
  - Validate CLI help text
  - Review API documentation
  - Duration: 2 hours

- [ ] **Release Notes Draft**
  - Complete v1.0 release notes from template
  - List all 22 implemented features
  - Document known issues (if any)
  - Write migration guide from matric-cli eval
  - Duration: 1 hour

**Deliverables**:
- Release candidate builds (Python + TypeScript)
- Test results report
- Reviewed documentation
- Draft release notes

**Gate Check**: All tests passing, coverage ≥80%, documentation complete

---

### Day 2 (Tuesday): Release Validation and Stakeholder Review

**Focus**: Independent validation and stakeholder sign-off

**Activities**:
- [ ] **TestPyPI Deployment**
  - Publish to TestPyPI: `uv publish --repository testpypi`
  - Install from TestPyPI in clean environment
  - Run smoke tests from TestPyPI package
  - Verify CLI functionality
  - Duration: 1.5 hours

- [ ] **Integration Testing**
  - Clone matric-cli to test environment
  - Install @matric/eval TypeScript bindings
  - Test subprocess integration
  - Verify JSON output parsing
  - Run matric-cli smoke tests with new eval
  - Duration: 2.5 hours

- [ ] **Stakeholder Review**
  - Share release notes with matric-cli team
  - Demonstrate key features
  - Gather feedback on documentation
  - Confirm deployment timeline
  - Duration: 1 hour

- [ ] **Security Scan**
  - Run pip-audit for vulnerabilities
  - Verify Docker sandbox isolation
  - Check for sensitive data in artifacts
  - Review SBOM for license compliance
  - Duration: 1 hour

- [ ] **Performance Benchmarking**
  - Baseline smoke tier runtime
  - Baseline quick tier runtime
  - Measure parallel execution speedup
  - Document resource usage (CPU, memory, disk)
  - Duration: 2 hours

**Deliverables**:
- TestPyPI validation report
- Integration test results
- Stakeholder feedback incorporated
- Security scan report
- Performance baseline metrics

**Gate Check**: TestPyPI installation works, integrations validated, no critical security issues

---

### Day 3 (Wednesday): Production Deployment

**Focus**: Release v1.0 to production repositories

**Activities**:
- [ ] **Final Version Tagging**
  - Update version in pyproject.toml: `1.0.0`
  - Update version in package.json: `1.0.0`
  - Commit version changes
  - Create git tag: `git tag -a v1.0.0 -m "Release v1.0.0"`
  - Push tag: `git push --tags`
  - Duration: 0.5 hours

- [ ] **PyPI Deployment**
  - Build final package: `uv build`
  - Verify dist/ artifacts
  - Publish to PyPI: `uv publish`
  - Verify package on PyPI.org
  - Test install: `pip install matric-eval==1.0.0`
  - Duration: 1 hour

- [ ] **npm Deployment**
  - Build TypeScript bindings
  - Test bindings locally
  - Publish to npm: `npm publish --access public`
  - Verify package on npmjs.com
  - Test install: `npm install @matric/eval@1.0.0`
  - Duration: 1 hour

- [ ] **Gitea Release**
  - Create release on Gitea
  - Upload release notes
  - Attach artifacts (wheels, tarballs)
  - Publish SBOM
  - Duration: 0.5 hours

- [ ] **Documentation Deployment**
  - Update README.md with installation badges
  - Publish user guide
  - Update project URLs
  - Create quick start guide
  - Duration: 2 hours

- [ ] **Announcement**
  - Post release announcement in team chat
  - Email matric-cli and matric-memory teams
  - Update project status in Gitea
  - Duration: 1 hour

**Deliverables**:
- v1.0.0 published to PyPI
- v1.0.0 published to npm
- Git release created
- Documentation live
- Stakeholders notified

**Gate Check**: Packages installable, documentation accessible, stakeholders informed

**Rollback Plan**: If critical issues discovered, yank from PyPI, remove npm version, notify stakeholders immediately

---

### Day 4 (Thursday): Post-Release Verification

**Focus**: Verify production deployment and integration success

**Activities**:
- [ ] **Installation Verification**
  - Clean install from PyPI on 3 platforms (Linux, macOS, Windows)
  - Verify dependencies resolve correctly
  - Test CLI on each platform
  - Document platform-specific issues
  - Duration: 2 hours

- [ ] **matric-cli Integration**
  - Update matric-cli to use @matric/eval@1.0.0
  - Run matric-cli test suite
  - Verify eval workflow works end-to-end
  - Create integration example in matric-cli docs
  - Duration: 2.5 hours

- [ ] **CI/CD Validation**
  - Update matric-eval CI to use published package
  - Verify smoke tests run in CI
  - Check nightly build status
  - Duration: 1 hour

- [ ] **Monitoring Setup**
  - Track PyPI download stats
  - Monitor issue tracker for new bug reports
  - Set up alerts for critical failures
  - Create support triage process
  - Duration: 1.5 hours

- [ ] **Support Readiness**
  - Prepare troubleshooting runbook
  - Document common errors and solutions
  - Create support email templates
  - Train matric-cli team on new eval features
  - Duration: 1 hour

**Deliverables**:
- Multi-platform verification report
- matric-cli integration validated
- Monitoring dashboard active
- Support runbook complete

**Gate Check**: All platforms working, matric-cli integration successful, monitoring active

---

### Day 5 (Friday): Support Handover and Hypercare Kickoff

**Focus**: Transition to support mode and begin hypercare

**Activities**:
- [ ] **Support Handover**
  - Review troubleshooting guide with matric-cli team
  - Demonstrate debugging techniques
  - Share common issue resolutions
  - Establish escalation path
  - Duration: 2 hours

- [ ] **User Acceptance Testing**
  - Coordinate UAT with matric-cli team
  - Validate real-world workflows
  - Gather initial user feedback
  - Document enhancement requests
  - Duration: 2 hours

- [ ] **Hypercare Planning**
  - Define hypercare monitoring checklist
  - Schedule daily check-ins (next 2 weeks)
  - Set response SLAs for issues
  - Prepare hotfix process
  - Duration: 1 hour

- [ ] **Lessons Learned Session**
  - Retrospective on Transition phase
  - Document deployment successes
  - Identify improvement opportunities
  - Update deployment procedures
  - Duration: 1 hour

- [ ] **v1.1 Planning Kickoff**
  - Review deferred P4 issues
  - Prioritize enhancement backlog
  - Estimate Rust bindings effort
  - Plan next iteration
  - Duration: 2 hours

**Deliverables**:
- Support handover complete
- UAT results documented
- Hypercare plan active
- Lessons learned captured
- v1.1 backlog prioritized

**Gate Check**: Support team ready, hypercare active, v1.1 roadmap defined

---

## Hypercare Period (Weeks 9-10)

### Duration
**2 weeks post-release** (14 calendar days from v1.0.0 deployment)

### Objectives
- Monitor production usage and stability
- Respond rapidly to critical issues
- Support early adopters
- Validate performance under real workloads
- Identify quick wins for v1.0.1 patch release

### Daily Activities

**Morning Check-in (15 minutes)**:
- Review issue tracker for new bugs
- Check PyPI download stats
- Monitor CI/CD health
- Review user feedback channels

**Issue Triage (30 minutes)**:
- Categorize new issues (bug, enhancement, question)
- Assign priority (P0-critical, P1-high, P2-medium, P3-low)
- Route to appropriate owner
- Update stakeholders on critical items

**Support Response (as needed)**:
- P0 issues: Respond within 4 hours, fix within 24 hours
- P1 issues: Respond within 8 hours, fix within 3 days
- P2 issues: Respond within 24 hours, plan for v1.0.1
- P3 issues: Acknowledge, plan for v1.1

**Weekly Review (1 hour, end of week)**:
- Summarize week's issues and resolutions
- Update health metrics (uptime, error rates)
- Communicate status to stakeholders
- Adjust hypercare plan if needed

### Success Metrics

**Availability**:
- 99%+ uptime (installation and execution success rate)
- No critical bugs blocking matric-cli integration

**Responsiveness**:
- All P0 issues resolved within 24 hours
- All P1 issues resolved within 3 days
- Support queries answered within 8 hours

**Adoption**:
- matric-cli successfully integrated
- 10+ PyPI downloads per day
- 3+ test evaluations run successfully

**Quality**:
- No data loss in checkpoint/resume
- No regression in benchmark accuracy
- Test coverage maintained ≥80%

### Escalation Procedures

**Critical Issue (P0)**:
- Examples: Data corruption, security vulnerability, installation failure
- Action: Immediate investigation, stakeholder notification, consider hotfix
- Timeline: 4-hour response, 24-hour resolution

**High Priority (P1)**:
- Examples: Benchmark failing, CLI crash, performance degradation
- Action: Investigation within 8 hours, fix plan documented
- Timeline: 8-hour response, 3-day resolution

**Rollback Trigger**:
- 3+ critical issues within 48 hours
- Security vulnerability (CVSS ≥7.0)
- Data loss confirmed
- Action: Yank PyPI release, publish rollback instructions, deploy v1.0.1 hotfix

### Communication Plan

**Daily**:
- Issue tracker updates
- Internal status log

**Weekly**:
- Summary email to matric-cli and matric-memory teams
- Health metrics dashboard

**End of Hypercare**:
- Final report with metrics, issues resolved, recommendations
- Transition to normal support mode

---

## Release Preparation Activities

### Pre-Release Checklist

**Code Quality**:
- [ ] All P1-P3 issues implemented and tested
- [ ] Test coverage ≥80% verified
- [ ] Linting passes: `ruff check .`
- [ ] Type checking passes: `mypy src/`
- [ ] No critical bugs in issue tracker
- [ ] Code review completed (self-review for solo dev)

**Testing**:
- [ ] Unit tests: 100% passing
- [ ] Integration tests: 100% passing
- [ ] Smoke tests: <2 minutes, 100% passing
- [ ] Quick tests: <20 minutes, 100% passing
- [ ] Checkpoint/resume tested with interruptions
- [ ] Parallel execution validated

**Documentation**:
- [ ] README.md installation guide complete
- [ ] CLAUDE.md accurate for AI assistance
- [ ] CLI help text comprehensive
- [ ] API documentation generated
- [ ] Troubleshooting guide written
- [ ] Migration guide from matric-cli eval
- [ ] Known issues documented

**Security**:
- [ ] pip-audit: No critical vulnerabilities
- [ ] Docker sandbox: Isolation verified
- [ ] Secrets: No credentials in code/artifacts
- [ ] SBOM: Generated and reviewed
- [ ] License compliance: All dependencies checked

**Release Artifacts**:
- [ ] pyproject.toml version updated
- [ ] package.json version updated
- [ ] CHANGELOG.md updated with v1.0.0 notes
- [ ] Git tag created: `v1.0.0`
- [ ] Wheel built: `dist/matric_eval-1.0.0-py3-none-any.whl`
- [ ] Tarball built: `dist/matric_eval-1.0.0.tar.gz`
- [ ] TypeScript bindings built

---

## Stakeholder Communication

### matric-cli Team

**Pre-Release**:
- Share release notes draft
- Demonstrate integration example
- Provide migration timeline
- Answer questions about API changes

**Release Day**:
- Announce v1.0.0 availability
- Share installation instructions
- Provide integration guide
- Offer pair programming session

**Post-Release**:
- Monitor integration success
- Respond to feedback
- Support troubleshooting
- Plan joint testing sessions

### matric-memory Team

**Pre-Release**:
- Inform about TypeScript-first approach
- Share Rust bindings roadmap (v1.1)
- Explain CLI-based integration option
- Gather requirements for v1.1

**Release Day**:
- Notify of v1.0.0 release
- Share CLI integration patterns
- Explain subprocess approach
- Set expectations for Rust bindings

**Post-Release**:
- Collect feedback for v1.1
- Prioritize Rust binding features
- Coordinate v1.1 timeline

### Project Stakeholders

**Weekly Status Updates**:
- Deployment progress
- Issue resolution metrics
- Adoption stats
- Next steps

**Release Announcement**:
- v1.0.0 feature highlights
- Installation instructions
- Getting started guide
- Support channels

---

## Support Handover

### Documentation Handover

**User Documentation**:
- Installation guide (pip/uv)
- Quick start tutorial
- CLI reference
- Configuration guide
- Troubleshooting guide

**Developer Documentation**:
- Architecture overview
- API reference
- Extension guide
- Contributing guidelines

**Operations Documentation**:
- Deployment procedures
- Monitoring setup
- Rollback procedures
- Hotfix process

### Knowledge Transfer

**Training Sessions** (with matric-cli team):
1. **Session 1: Installation and Basic Usage** (30 min)
   - Installation methods
   - CLI commands
   - Tiered evaluation
   - Output interpretation

2. **Session 2: Advanced Features** (45 min)
   - Checkpoint/resume
   - Custom tests
   - Parallel execution
   - Configuration options

3. **Session 3: Troubleshooting** (30 min)
   - Common errors
   - Debug logging
   - Issue reporting
   - Workarounds

### Support Channels

**Issue Tracker**:
- https://git.integrolabs.net/roctinam/matric-eval/issues
- For bugs, feature requests, questions

**Email**:
- dev@integrolabs.net
- For urgent support requests

**Documentation**:
- README.md for quick reference
- docs/ for comprehensive guides

**Source Code**:
- GitHub/Gitea repository
- For developers extending functionality

---

## Final Acceptance Tests

### End-to-End Validation

**Test Scenario 1: Fresh Installation**:
1. Clean Python environment (venv)
2. `pip install matric-eval`
3. `matric-eval --version`
4. `matric-eval --tier smoke --model llama3.2:3b`
5. Verify results in `results/smoke-*.json`

**Expected**: Installation succeeds, smoke tests complete in <2 min, results valid

**Test Scenario 2: Checkpoint/Resume**:
1. Start quick tier: `matric-eval --tier quick --model llama3.2:3b`
2. Interrupt after 5 models (Ctrl+C)
3. Verify checkpoint in `results/quick-*.meta.json`
4. Resume: `matric-eval --resume results/quick-*.meta.json`
5. Verify gap detection and completion

**Expected**: No duplicate work, all models evaluated, results complete

**Test Scenario 3: Custom Tests**:
1. Run custom matric tests: `matric-eval --tier custom --app matric-cli`
2. Verify tool calling scenarios execute
3. Check 5D scoring results
4. Validate output format

**Expected**: All custom tests pass, scoring accurate, results parseable

**Test Scenario 4: matric-cli Integration**:
1. Install @matric/eval in matric-cli
2. Run matric-cli evaluation command
3. Verify subprocess spawns correctly
4. Check JSON output parsing
5. Validate integration works end-to-end

**Expected**: matric-cli successfully uses matric-eval, results displayed

**Test Scenario 5: Parallel Execution**:
1. Run full tier with parallelization: `matric-eval --tier full --parallel 4`
2. Monitor resource usage
3. Verify checkpoint state with concurrent writes
4. Compare runtime to sequential execution

**Expected**: 50%+ speedup, no state corruption, results accurate

### Acceptance Criteria

All scenarios must pass with:
- Zero data loss
- Zero critical bugs
- Performance within targets
- Documentation accurate
- Integration successful

---

## Hypercare Monitoring Plan

### Daily Health Checks

**Morning Standup Checklist**:
- [ ] Check issue tracker for overnight reports
- [ ] Review PyPI download stats
- [ ] Verify CI/CD pipeline status
- [ ] Check error logs for anomalies
- [ ] Review user feedback channels

**Monitoring Metrics**:

**Installation Success Rate**:
- Track: pip install failures from logs
- Target: 99%+ success
- Alert: <95% success

**Execution Success Rate**:
- Track: CLI exit codes, error logs
- Target: 95%+ successful runs
- Alert: <90% success

**Performance**:
- Track: Smoke tier runtime
- Target: <2 minutes
- Alert: >3 minutes

**Issue Volume**:
- Track: New issues per day
- Target: <5 issues/day during hypercare
- Alert: >10 issues/day

**Critical Bugs**:
- Track: P0 severity issues
- Target: 0 critical bugs
- Alert: Any P0 issue

### Weekly Health Report

**Metrics Summary**:
- Total downloads
- Total installations
- Total evaluations run
- Average runtime (smoke/quick/full)
- Issues opened/closed
- User satisfaction (if surveys available)

**Issue Trends**:
- Most common issues
- Bug categories (installation, execution, results)
- Feature requests
- Documentation gaps

**Actions Taken**:
- Issues resolved
- Hotfixes deployed
- Workarounds provided
- Documentation updates

**Recommendations**:
- v1.0.1 patch priorities
- v1.1 feature candidates
- Process improvements

---

## Transition Gate Criteria

### Release Criteria

- [x] All P1-P3 Construction issues implemented (verified in Week 7)
- [ ] Test coverage ≥80% confirmed
- [ ] PyPI package published and installable
- [ ] npm package published and installable
- [ ] Git release created with notes
- [ ] Documentation complete and accessible

### Support Criteria

- [ ] Troubleshooting guide complete
- [ ] Support handover accepted by matric-cli team
- [ ] Escalation procedures documented
- [ ] Monitoring dashboard active

### Integration Criteria

- [ ] matric-cli integration tested and working
- [ ] TypeScript bindings validated
- [ ] Example integration code provided
- [ ] Migration guide from old eval complete

### Hypercare Criteria

- [ ] Daily monitoring checklist active
- [ ] Response SLAs defined
- [ ] Escalation procedures tested
- [ ] Rollback plan validated

### Documentation Criteria

- [ ] Installation guide verified on 3 platforms
- [ ] Quick start tutorial complete
- [ ] CLI reference accurate
- [ ] API documentation generated
- [ ] Known issues documented

---

## Deliverables Summary

### Week 8 Deliverables

**Day 1**:
- Release candidate builds
- Final test results
- Draft release notes

**Day 2**:
- TestPyPI validation
- Integration test results
- Security scan report
- Performance baseline

**Day 3**:
- v1.0.0 on PyPI
- v1.0.0 on npm
- Git release
- Documentation live
- Announcement sent

**Day 4**:
- Multi-platform verification
- matric-cli integration validated
- Monitoring active
- Support runbook

**Day 5**:
- Support handover complete
- UAT results
- Hypercare active
- v1.1 backlog

### Hypercare Deliverables

**Weekly**:
- Health report
- Issue resolution summary
- Stakeholder communication

**End of Hypercare**:
- Final transition report
- Lessons learned
- v1.0.1/v1.1 recommendations
- Transition to normal support

---

## Risks and Mitigation

### Deployment Risks

**Risk**: PyPI/npm deployment failures
- **Mitigation**: Use TestPyPI first, validate builds locally
- **Rollback**: Retry deployment, use alternative distribution

**Risk**: Critical bug discovered during hypercare
- **Mitigation**: Thorough pre-release testing, rapid hotfix process
- **Rollback**: Yank package, publish v1.0.1 hotfix immediately

**Risk**: matric-cli integration breaks unexpectedly
- **Mitigation**: Pre-release integration testing, coordinate with team
- **Rollback**: Provide workaround, release patch

### Support Risks

**Risk**: Overwhelming support volume during hypercare
- **Mitigation**: Comprehensive documentation, clear troubleshooting guide
- **Rollback**: Extend hypercare period, recruit additional support

**Risk**: Knowledge gaps in handover
- **Mitigation**: Detailed documentation, pair programming sessions
- **Rollback**: Additional training sessions, extended support overlap

---

## Success Metrics

### Deployment Success

- [ ] v1.0.0 published on schedule (Day 3)
- [ ] Zero critical bugs on release day
- [ ] matric-cli integration successful (Day 4)
- [ ] Documentation feedback positive

### Adoption Success

- [ ] 10+ PyPI downloads by end of Week 8
- [ ] matric-cli using matric-eval in production
- [ ] 3+ successful evaluations run by external users

### Quality Success

- [ ] Test coverage maintained ≥80%
- [ ] No data loss incidents
- [ ] No security vulnerabilities
- [ ] Performance targets met

### Support Success

- [ ] All P0 issues resolved within 24 hours
- [ ] All P1 issues resolved within 3 days
- [ ] Support handover accepted by matric-cli team
- [ ] Hypercare monitoring active

---

## Post-Transition

### Normal Support Mode

After hypercare period ends, transition to normal support mode:

**Issue Response**:
- P0: 24-hour response, 48-hour fix
- P1: 48-hour response, 1-week fix
- P2: 1-week response, next minor release
- P3: Acknowledged, backlog for consideration

**Maintenance Releases**:
- **Patch (v1.0.x)**: Bug fixes, security updates, monthly or as needed
- **Minor (v1.x.0)**: New features, enhancements, quarterly
- **Major (v2.0.0)**: Breaking changes, as required

### v1.1 Planning

**Deferred P4 Features** (from Construction phase):
- Issue #15: Leaderboard and reporting dashboard
- Issue #17: Extended benchmarks (SWE-bench, GPQA)
- Issue #19: Contamination detection
- Issue #20: Historical trend analysis
- Issue #16 (complete): Full TypeScript bindings

**New Features** (from hypercare feedback):
- Rust bindings for matric-memory
- Enhanced parallel execution
- Additional public benchmarks
- Custom scoring templates

**Timeline**: 4-6 weeks post-v1.0 release

---

## Document Metadata

**Document Control**:
- **Version**: 1.0
- **Created**: 2026-01-24
- **Phase**: Transition (Week 8)
- **Owner**: Solo Python Developer (roctinam)
- **Status**: PENDING (awaits Construction completion)

**Referenced Artifacts**:
- Construction Summary: `.aiwg/planning/construction-summary.md`
- Deployment Plan: `.aiwg/deployment/deployment-plan.md`
- Release Notes Template: `.aiwg/deployment/release-notes-template.md`
- Gate Criteria: `.aiwg/gates/gate-transition.md`

**Next Review**: End of Week 7 (Construction Gate)

---

**END OF TRANSITION PHASE PLAN**
