# Vision

GMV OS is a knowledge operating system.

# Current Architecture Phase

The active phase is **Core Integrity**. The current repository provides a Core foundation and partial ingestion scaffolding; it does not yet constitute the Intelligence, Reasoning, Decision, or autonomous workflow layers described by the long-term product vision.

# Layers

User
↓
CLI
↓
Services
↓
Engines
↓
Core
↓
SQLite
↓
Resources

# Core Components

- Objects
- Relations
- Events
- Resources
- Import Queue
- Plugin Registry
- Service Registry

# Development Principles

1. One responsibility per Engine.
2. One task per commit.
3. Tests before commit.
4. Core changes only when strictly necessary.
5. Never lose a document.
6. Everything has an OID.
7. Every action creates an Event.
8. Everything is traceable.
9. Architecture before implementation.
10. Small incremental commits.

# Development Workflow

Architecture
↓
Backlog
↓
Sprint
↓
Implementation
↓
Tests
↓
Review
↓
Merge

# Architecture Gates

Reasoning, Decision, and autonomous workflow execution are architectural targets, not active implementation scope.

- Reasoning requires completed Core Integrity, Reliability, Data / Database, Automation, and governed Knowledge gates, including stable identity, provenance, evidence, and graph-quality controls.
- Decision capabilities require an approved Reasoning evaluation model, explainable evidence, human-review policy, authorization boundaries, and outcome tracking.
- Autonomous workflow execution requires canonical Events, verified backup and recovery, strict health signals, safe queue claim/retry semantics, auditable authorization, and explicit human-control boundaries.

No component may bypass these gates merely because an interface, command, schema, or architecture document exists.

# Architecture Decision: Defer Application Caching

**Decision ID:** ADR-S001-01

**Status:** Accepted for the Core Integrity phase

**Related backlog item:** `PERF-007`

## Context

GMV OS does not yet have one fully enforced source of truth, complete Event-driven invalidation rules, or measured workloads demonstrating a need for application caching. Caching current inconsistencies would create stale knowledge and obscure authority defects.

## Decision

No application cache will be introduced during Core Integrity. SQLite and governed Resource state remain authoritative. Query optimization may use measured SQL and indexing work approved by the roadmap, but it must not create an independent application-level source of truth.

## Reconsideration Gate

A cache may be proposed only after authoritative ownership and canonical Events are enforced, invalidation inputs are explicit, measured performance evidence justifies it, and deterministic rebuild and equivalence tests exist. Each future cache requires its own reviewed implementation task.
