import { http } from "./http";
import type { ApiEnvelope, NotificationItem } from "../types";

export async function getUnreadNotificationCount(): Promise<number> {
  const response = await http.get<ApiEnvelope<{ unread_count: number }>>("/notifications/unread-count");
  return Number(response.data.data.unread_count ?? 0);
}

export async function listNotifications(params?: {
  unread_only?: boolean;
  limit?: number;
  offset?: number;
}) {
  const response = await http.get<ApiEnvelope<NotificationItem[]>>("/notifications", {
    params
  });
  const meta = (response.data.meta ?? {}) as {
    total?: number;
    limit?: number;
    offset?: number;
    has_more?: boolean;
  };
  return {
    data: response.data.data,
    meta: {
      total: Number(meta.total ?? 0),
      limit: Number(meta.limit ?? params?.limit ?? 20),
      offset: Number(meta.offset ?? params?.offset ?? 0),
      has_more: Boolean(meta.has_more ?? false)
    }
  };
}

export async function readNotification(notificationId: number): Promise<NotificationItem> {
  const response = await http.post<ApiEnvelope<NotificationItem>>(`/notifications/${notificationId}/read`);
  return response.data.data;
}

export async function readAllNotifications(): Promise<{ updated: number }> {
  const response = await http.post<ApiEnvelope<{ updated: number }>>("/notifications/read-all");
  return response.data.data;
}
