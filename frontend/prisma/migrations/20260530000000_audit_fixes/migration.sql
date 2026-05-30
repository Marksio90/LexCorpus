-- AddColumn: PrivateDocument.deletedAt (soft-delete)
ALTER TABLE "PrivateDocument" ADD COLUMN "deletedAt" TIMESTAMP(3);

-- CreateIndex: PrivateDocument.deletedAt
CREATE INDEX "PrivateDocument_deletedAt_idx" ON "PrivateDocument"("deletedAt");

-- AddColumn: WidgetConfig.expiresAt (token expiry)
ALTER TABLE "WidgetConfig" ADD COLUMN "expiresAt" TIMESTAMP(3);

-- CreateIndex: UsageLog.date (range queries)
CREATE INDEX "UsageLog_date_idx" ON "UsageLog"("date" DESC);
