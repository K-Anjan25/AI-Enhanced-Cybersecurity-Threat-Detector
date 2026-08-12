export interface Column {
  id: string | number;
  label: string;
  minWidth?: number;
  align?: "right" | "center" | "left";
}

export class ThreatLogRow {
  id: string;
  timestamp: string;
  threatLevel: string;
  sourceIp: string;
  destinationIp: string;
  signature: string;
  status: string;

  constructor(
    id: string,
    timestamp: string,
    threatLevel: string,
    sourceIp: string,
    destinationIp: string,
    signature: string,
    status: string
  ) {
    this.id = id;
    this.timestamp = timestamp;
    this.threatLevel = threatLevel;
    this.sourceIp = sourceIp;
    this.destinationIp = destinationIp;
    this.signature = signature;
    this.status = status;
  }
}

export class SystemAuditRow {
  id: string;
  timestamp: string;
  username: string;
  action: string;
  details: string;

  constructor(
    id: string,
    timestamp: string,
    username: string,
    action: string,
    details: string
  ) {
    this.id = id;
    this.timestamp = timestamp;
    this.username = username;
    this.action = action;
    this.details = details;
  }
}

export class UserManagementRow {
  id: string;
  username: string;
  email: string;
  role: string;
  createdDate: string;

  constructor(
    id: string,
    username: string,
    email: string,
    role: string,
    createdDate: string
  ) {
    this.id = id;
    this.username = username;
    this.email = email;
    this.role = role;
    this.createdDate = createdDate;
  }
}

export type TableRow = InstanceType<
  typeof ThreatLogRow | typeof SystemAuditRow | typeof UserManagementRow
>;