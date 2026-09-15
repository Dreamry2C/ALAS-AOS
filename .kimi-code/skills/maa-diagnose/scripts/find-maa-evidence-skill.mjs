#!/usr/bin/env node

import { execFileSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
const DIAGNOSE_ROOT = path.resolve(
  process.env.MAA_DIAGNOSE_ROOT ?? path.join(SCRIPT_DIR, ".."),
);
const UPSTREAM_SKILL = path.join("skills", "maa-evidence", "SKILL.md");
const PACKAGE_NAME = "maa-evidence-kit";

function parseArgs(argv) {
  const roots = [];
  let ambient = true;
  for (let index = 0; index < argv.length; index += 1) {
    const argument = argv[index];
    if (argument === "--no-ambient") {
      ambient = false;
      continue;
    }
    if (argument !== "--root" || !argv[index + 1] || argv[index + 1].startsWith("--")) {
      throw new Error(
        "Usage: find-maa-evidence-skill.mjs [--no-ambient] [--root PATH ...]",
      );
    }
    roots.push(path.resolve(argv[index + 1]));
    index += 1;
  }
  return { roots, ambient };
}

function canonical(candidate) {
  try {
    return fs.realpathSync.native(candidate);
  } catch {
    return path.resolve(candidate);
  }
}

function isFile(candidate) {
  try {
    return fs.statSync(candidate).isFile();
  } catch {
    return false;
  }
}

function addCandidate(list, seen, candidate, source, precedence) {
  const resolved = canonical(candidate);
  const key = process.platform === "win32" ? resolved.toLowerCase() : resolved;
  if (seen.has(key)) return;
  seen.add(key);
  list.push({ path: resolved, source, precedence });
}

function ancestors(start) {
  const result = [];
  let current = path.resolve(start);
  while (true) {
    result.push(current);
    const parent = path.dirname(current);
    if (parent === current) return result;
    current = parent;
  }
}

function packageInfo(candidate) {
  const packageJson = path.join(candidate, "package.json");
  if (!isFile(packageJson)) return undefined;
  try {
    const metadata = JSON.parse(fs.readFileSync(packageJson, "utf8"));
    if (metadata.name !== PACKAGE_NAME) return undefined;
    return { root: canonical(candidate), version: metadata.version ?? null };
  } catch {
    return undefined;
  }
}

function runPackageManager(command, args) {
  try {
    const executable = process.platform === "win32" ? `${command}.cmd` : command;
    return execFileSync(executable, args, {
      encoding: "utf8",
      shell: process.platform === "win32",
      stdio: ["ignore", "pipe", "ignore"],
      timeout: 5000,
    });
  } catch {
    return undefined;
  }
}

function globalPackagePaths(manager) {
  if (manager === "npm") {
    const root = runPackageManager(manager, ["root", "-g"])?.trim();
    return root ? [path.join(root, PACKAGE_NAME)] : [];
  }

  const output = runPackageManager(manager, [
    "list",
    "-g",
    "--json",
    PACKAGE_NAME,
  ]);
  if (!output) return [];

  try {
    const report = JSON.parse(output);
    const entries = Array.isArray(report) ? report : [report];
    return entries
      .flatMap((entry) => Object.values(entry.dependencies ?? {}))
      .filter((dependency) => dependency.path)
      .map((dependency) => dependency.path);
  } catch {
    return [];
  }
}

function skillFromExplicitRoot(root) {
  const candidates = [
    root,
    path.join(root, "SKILL.md"),
    path.join(root, "maa-evidence", "SKILL.md"),
    path.join(root, UPSTREAM_SKILL),
  ];
  return candidates.find((candidate) => isFile(candidate));
}

function isUpstreamSkill(candidate) {
  if (!isFile(candidate)) return false;
  if (canonical(candidate).startsWith(`${canonical(DIAGNOSE_ROOT)}${path.sep}`)) return false;
  const head = fs.readFileSync(candidate, "utf8").slice(0, 4096);
  return /^---\r?\n[\s\S]*?^name:\s*["']?maa-evidence["']?\s*$/m.test(head);
}

function main() {
  const { roots: explicitRoots, ambient } = parseArgs(process.argv.slice(2));
  const skillCandidates = [];
  const packageCandidates = [];
  const seenSkills = new Set();
  const seenPackages = new Set();

  for (const root of explicitRoots) {
    if (packageInfo(root)) {
      addCandidate(packageCandidates, seenPackages, root, "explicit-package", 0);
    } else {
      const skill = skillFromExplicitRoot(root);
      if (skill) addCandidate(skillCandidates, seenSkills, skill, "explicit", 0);
      const packageRoot = path.dirname(root);
      if (packageInfo(packageRoot)) addCandidate(packageCandidates, seenPackages, packageRoot, "explicit-package", 0);
    }
  }

  skillCandidates.sort((left, right) => left.precedence - right.precedence);
  for (const candidate of skillCandidates) {
    if (isUpstreamSkill(candidate.path)) {
      console.log(JSON.stringify({ status: "found", source: candidate.source, skillPath: candidate.path, packageRoot: null, packageVersion: null }, null, 2));
      return;
    }
  }

  packageCandidates.sort((left, right) => left.precedence - right.precedence);
  let explicitPackageWithoutSkill;
  for (const candidate of packageCandidates) {
    const info = packageInfo(candidate.path);
    if (!info) continue;
    const skillPath = path.join(info.root, UPSTREAM_SKILL);
    if (isUpstreamSkill(skillPath)) {
      console.log(JSON.stringify({ status: "found", source: candidate.source, skillPath, packageRoot: info.root, packageVersion: info.version }, null, 2));
      return;
    }
    explicitPackageWithoutSkill ??= { candidate, info };
  }
  if (explicitPackageWithoutSkill) {
    console.log(JSON.stringify({ status: "package-without-skill", source: explicitPackageWithoutSkill.candidate.source, skillPath: null, packageRoot: explicitPackageWithoutSkill.info.root, packageVersion: explicitPackageWithoutSkill.info.version }, null, 2));
    return;
  }
  if (!ambient) {
    console.log(JSON.stringify({ status: "not-found", source: null, skillPath: null, packageRoot: null, packageVersion: null }, null, 2));
    return;
  }

  const home = os.homedir();
  const projectRoots = ancestors(process.cwd());
  const skillRoots = [];
  for (const root of projectRoots) {
    skillRoots.push(path.join(root, ".codex", "skills"), path.join(root, ".agents", "skills"), path.join(root, ".claude", "skills"));
  }
  if (process.env.CODEX_HOME) skillRoots.push(path.join(process.env.CODEX_HOME, "skills"));
  skillRoots.push(path.join(home, ".codex", "skills"), path.join(home, ".agents", "skills"), path.join(home, ".claude", "skills"));

  for (const root of skillRoots) {
    addCandidate(skillCandidates, seenSkills, path.join(root, "maa-evidence", "SKILL.md"), "installed-skill", 1);
  }

  for (const root of projectRoots) {
    addCandidate(packageCandidates, seenPackages, path.join(root, "node_modules", PACKAGE_NAME), "project-package", 2);
  }
  for (const manager of ["npm", "pnpm"]) {
    for (const root of globalPackagePaths(manager)) {
      addCandidate(packageCandidates, seenPackages, root, `${manager}-global-package`, 3);
    }
  }

  skillCandidates.sort((left, right) => left.precedence - right.precedence);
  for (const candidate of skillCandidates) {
    if (isUpstreamSkill(candidate.path)) {
      console.log(JSON.stringify({ status: "found", source: candidate.source, skillPath: candidate.path, packageRoot: null, packageVersion: null }, null, 2));
      return;
    }
  }

  packageCandidates.sort((left, right) => left.precedence - right.precedence);
  let packageWithoutSkill;
  for (const candidate of packageCandidates) {
    const info = packageInfo(candidate.path);
    if (!info) continue;
    const skillPath = path.join(info.root, UPSTREAM_SKILL);
    if (isUpstreamSkill(skillPath)) {
      console.log(JSON.stringify({ status: "found", source: candidate.source, skillPath, packageRoot: info.root, packageVersion: info.version }, null, 2));
      return;
    }
    packageWithoutSkill ??= { candidate, info };
  }

  if (packageWithoutSkill) {
    console.log(JSON.stringify({ status: "package-without-skill", source: packageWithoutSkill.candidate.source, skillPath: null, packageRoot: packageWithoutSkill.info.root, packageVersion: packageWithoutSkill.info.version }, null, 2));
    return;
  }

  console.log(JSON.stringify({ status: "not-found", source: null, skillPath: null, packageRoot: null, packageVersion: null }, null, 2));
}

try {
  main();
} catch (error) {
  console.error(error instanceof Error ? error.message : String(error));
  process.exitCode = 1;
}
