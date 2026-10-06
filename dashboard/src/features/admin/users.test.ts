/**
 * The users model (T-410, R-53).
 *
 * The acceptance criterion is *the last `admin` cannot self-demote*, and the server
 * enforces it. What this file tests is the half the server cannot: that the screen
 * speaks about the rule from the server's own number rather than from a count of its
 * own. So the cases that matter are the ones where the two would disagree — a disabled
 * admin (which does **not** count towards the floor), a directory with two admins (no
 * row is marked), and a count the server did not send (nothing is marked, rather than
 * everything).
 */
import { describe, expect, it } from 'vitest';

import type { AdminUser, RoleInfo, UserList } from '../../api/admin';
import {
  CAPABILITY_LABELS,
  LAST_ADMIN_NOTE,
  ROLE_LABELS,
  roleChangeRequired,
  roleChoices,
  userRows,
  userSummary,
} from './users';

function user(over: Partial<AdminUser> = {}): AdminUser {
  return {
    id: 1,
    email: 'a@example.test',
    role: 'admin',
    created_at: '2026-01-01T00:00:00Z',
    disabled_at: null,
    ...over,
  };
}

function directory(items: AdminUser[], activeAdmins: number): UserList {
  return { items, count: items.length, active_admins: activeAdmins };
}

describe('userRows', () => {
  it('marks the single active admin from the server’s count, not from the rows', () => {
    const rows = userRows(
      directory([user(), user({ id: 2, email: 'v@example.test', role: 'viewer' })], 1),
    );
    expect(rows[0]?.lastActiveAdmin).toBe(true);
    expect(rows[0]?.demotionRefusal).toBe(LAST_ADMIN_NOTE);
    expect(rows[1]?.lastActiveAdmin).toBe(false);
    expect(rows[1]?.demotionRefusal).toBeNull();
  });

  it('marks nobody when the deployment has two admins', () => {
    const rows = userRows(directory([user(), user({ id: 2, email: 'b@example.test' })], 2));
    expect(rows.map((row) => row.lastActiveAdmin)).toEqual([false, false]);
  });

  it('does not treat a disabled admin as the last one', () => {
    // A disabled account cannot sign in, so it is not what the floor protects. The
    // server counts active admins only; this asserts the screen reads that number
    // rather than counting `role === 'admin'` itself.
    const rows = userRows(
      directory([user({ disabled_at: '2026-02-01T00:00:00Z' }), user({ id: 2, role: 'admin' })], 1),
    );
    expect(rows[0]?.disabled).toBe(true);
    expect(rows[0]?.lastActiveAdmin).toBe(false);
    expect(rows[1]?.lastActiveAdmin).toBe(true);
  });

  it('marks nobody when the count is missing, rather than everybody', () => {
    const broken = { items: [user()], count: 1 } as unknown as UserList;
    expect(userRows(broken)[0]?.lastActiveAdmin).toBe(false);
  });

  it('renders a role it does not know rather than dropping the row', () => {
    const rows = userRows(directory([user({ role: 'auditor' })], 0));
    expect(rows[0]?.role).toBe('auditor');
    expect(rows[0]?.roleLabel).toBe('auditor');
  });

  it('turns a null disabled_at into an empty string, never "null"', () => {
    expect(userRows(directory([user()], 1))[0]?.disabledAt).toBe('');
  });

  it('is empty for an unread directory', () => {
    expect(userRows(undefined)).toEqual([]);
  });
});

describe('userSummary', () => {
  it('counts the admins the server reported', () => {
    const summary = userSummary(directory([user(), user({ id: 2, role: 'viewer' })], 1));
    expect(summary.count).toBe(2);
    expect(summary.activeAdmins).toBe(1);
    expect(summary.stranded).toBe(false);
    expect(summary.note).toContain('1 active admin of 2 accounts');
  });

  it('pluralises without lying about the count', () => {
    const summary = userSummary(directory([user(), user({ id: 2 })], 2));
    expect(summary.note).toContain('2 active admins of 2 accounts');
  });

  it('says a directory with accounts and no active admin is stranded', () => {
    // This is a deployment state, not a permission: the sentence says so, because
    // a reader who saw "0 admins" beside a working screen would trust the screen.
    const summary = userSummary(directory([user({ role: 'viewer' })], 0));
    expect(summary.stranded).toBe(true);
    expect(summary.note).toContain('No active admin is registered');
  });

  it('does not call an empty directory stranded', () => {
    expect(userSummary(directory([], 0)).stranded).toBe(false);
  });
});

describe('roleChoices', () => {
  const listed: RoleInfo[] = [
    { role: 'admin', capabilities: ['read', 'users'] },
    { role: 'viewer', capabilities: ['read'] },
    { role: 'analyst', capabilities: ['read', 'verdict'] },
    { role: 'responder', capabilities: ['read', 'verdict', 'export'] },
  ];

  it('orders the roles R-53’s way regardless of the order they arrived in', () => {
    expect(roleChoices(listed).map((choice) => choice.role)).toEqual([
      'viewer',
      'analyst',
      'responder',
      'admin',
    ]);
  });

  it('describes capabilities in words, falling back to the raw name', () => {
    const choices = roleChoices(listed);
    expect(choices[3]?.describes).toBe(
      `${CAPABILITY_LABELS['read']}, ${CAPABILITY_LABELS['users']}`,
    );
    const unknown = roleChoices([{ role: 'x', capabilities: ['teleport'] }]);
    expect(unknown[0]?.describes).toBe('teleport');
  });

  it('appends a role the server described but this build does not know', () => {
    const choices = roleChoices([...listed, { role: 'auditor', capabilities: ['read'] }]);
    expect(choices.map((choice) => choice.role)).toContain('auditor');
  });

  it('has labels for every role R-53 names', () => {
    for (const role of ['viewer', 'analyst', 'responder', 'admin']) {
      expect(ROLE_LABELS[role]).toBeDefined();
    }
  });
});

describe('roleChangeRequired', () => {
  it('is false for the role the account already holds', () => {
    expect(roleChangeRequired('admin', 'admin')).toBe(false);
  });

  it('is false when nothing has been chosen yet', () => {
    expect(roleChangeRequired('admin', null)).toBe(false);
  });

  it('is true for a different role, in either direction', () => {
    expect(roleChangeRequired('admin', 'viewer')).toBe(true);
    expect(roleChangeRequired('viewer', 'admin')).toBe(true);
  });
});
