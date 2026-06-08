// src/pages/DashboardPage.tsx
import React, { useCallback, useEffect, useMemo, useState } from "react";
import api from "../api/client";
import { useAuth } from "../context/AuthContext";
import InvoiceModal from "../components/InvoiceModal";

export interface InvoiceDetailCreate {
  id_number: number;
  id_description: string;
  id_qty: number;
  id_rate: number;
  id_sale_tax?: number;
  id_adress?: string;
  id_adress2?: string;
}

export interface InvoiceCreate {
  i_name: string;
  i_inscription?: string;
  i_email?: string;
  i_address?: string;
  i_serie?: string;
  i_date: string;
  i_billto?: string;
  i_total: number;
  i_is_pay: boolean;
  details: InvoiceDetailCreate[];
}

export interface InvoiceRead {
  i_id: string;
  i_name: string;
  i_inscription?: string | null;
  i_email?: string | null;
  i_address?: string | null;
  i_serie?: string | null;
  i_date: string;
  i_billto?: string | null;
  i_total: number;
  i_is_pay: boolean;
  i_u_id: string;
  i_create_at: string;
}

interface InvoiceDetailRead extends InvoiceDetailCreate {
  id_id: string;
  id_create_at: string;
}

interface InvoiceWithDetailsRead extends InvoiceRead {
  details: InvoiceDetailRead[];
}

interface InvoiceSummaryRead {
  total: number;
  total_year: number;
  total_month: number;
  total_last_month: number;
}

interface InvoiceSummaryCounts {
  total: number;
  total_year: number;
  total_month: number;
  total_last_month: number;
}

type SummaryKey = keyof InvoiceSummaryRead;

interface SummaryBreakdownItem {
  paidTotal: number;
  paidCount: number;
  pendingTotal: number;
  pendingCount: number;
}

type SummaryBreakdown = Record<SummaryKey, SummaryBreakdownItem>;

const PAGE_SIZE_OPTIONS = [10, 25, 50];
const EMPTY_SUMMARY: InvoiceSummaryRead = {
  total: 0,
  total_year: 0,
  total_month: 0,
  total_last_month: 0,
};
const EMPTY_SUMMARY_COUNTS: InvoiceSummaryCounts = {
  total: 0,
  total_year: 0,
  total_month: 0,
  total_last_month: 0,
};
const EMPTY_BREAKDOWN_ITEM: SummaryBreakdownItem = {
  paidTotal: 0,
  paidCount: 0,
  pendingTotal: 0,
  pendingCount: 0,
};
const DashboardPage: React.FC = () => {
  const { logout } = useAuth();
  const [invoices, setInvoices] = useState<InvoiceRead[]>([]);
  const [summary, setSummary] = useState<InvoiceSummaryRead>(EMPTY_SUMMARY);
  const [summaryCounts, setSummaryCounts] =
    useState<InvoiceSummaryCounts>(EMPTY_SUMMARY_COUNTS);
  const [loading, setLoading] = useState(false);
  const [pageSize, setPageSize] = useState(25);
  const [currentPage, setCurrentPage] = useState(1);
  const [modalOpen, setModalOpen] = useState(false);
  const [editingInvoiceId, setEditingInvoiceId] = useState<string | null>(null);
  const [editingInvoice, setEditingInvoice] = useState<InvoiceCreate | null>(null);
  const [pdfUrl, setPdfUrl] = useState<string | null>(null);

  const totalPages = Math.max(1, Math.ceil(invoices.length / pageSize));
  const pagedInvoices = useMemo(() => {
    const start = (currentPage - 1) * pageSize;
    return invoices.slice(start, start + pageSize);
  }, [currentPage, invoices, pageSize]);

  const summaryBreakdown = useMemo<SummaryBreakdown>(() => {
    const now = new Date();
    const currentYear = now.getFullYear();
    const currentMonth = now.getMonth();
    const lastMonthDate = new Date(currentYear, currentMonth - 1, 1);
    const lastMonthYear = lastMonthDate.getFullYear();
    const lastMonth = lastMonthDate.getMonth();

    const nextBreakdown: SummaryBreakdown = {
      total: { ...EMPTY_BREAKDOWN_ITEM },
      total_year: { ...EMPTY_BREAKDOWN_ITEM },
      total_month: { ...EMPTY_BREAKDOWN_ITEM },
      total_last_month: { ...EMPTY_BREAKDOWN_ITEM },
    };

    const addInvoiceToBucket = (key: SummaryKey, invoice: InvoiceRead) => {
      const amount = Number(invoice.i_total) || 0;
      const bucket = nextBreakdown[key];

      if (invoice.i_is_pay) {
        bucket.paidTotal += amount;
        bucket.paidCount += 1;
      } else {
        bucket.pendingTotal += amount;
        bucket.pendingCount += 1;
      }
    };

    invoices.forEach((invoice) => {
      const invoiceDate = new Date(`${invoice.i_date}T00:00:00`);
      const invoiceYear = invoiceDate.getFullYear();
      const invoiceMonth = invoiceDate.getMonth();

      addInvoiceToBucket("total", invoice);

      if (invoiceYear === currentYear) {
        addInvoiceToBucket("total_year", invoice);
      }

      if (invoiceYear === currentYear && invoiceMonth === currentMonth) {
        addInvoiceToBucket("total_month", invoice);
      }

      if (invoiceYear === lastMonthYear && invoiceMonth === lastMonth) {
        addInvoiceToBucket("total_last_month", invoice);
      }
    });

    return nextBreakdown;
  }, [invoices]);

  const formatCurrency = (value: number) =>
    value.toLocaleString("en-US", {
      style: "currency",
      currency: "USD",
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });

  const normalizeSummary = (data: InvoiceSummaryRead): InvoiceSummaryRead => ({
    total: Number(data.total) || 0,
    total_year: Number(data.total_year) || 0,
    total_month: Number(data.total_month) || 0,
    total_last_month: Number(data.total_last_month) || 0,
  });

  const calculateSummary = (items: InvoiceRead[]): InvoiceSummaryRead => {
    const now = new Date();
    const currentYear = now.getFullYear();
    const currentMonth = now.getMonth();
    const lastMonthDate = new Date(currentYear, currentMonth - 1, 1);
    const lastMonthYear = lastMonthDate.getFullYear();
    const lastMonth = lastMonthDate.getMonth();

    return items.reduce<InvoiceSummaryRead>((acc, invoice) => {
      const total = Number(invoice.i_total) || 0;
      const invoiceDate = new Date(`${invoice.i_date}T00:00:00`);
      const invoiceYear = invoiceDate.getFullYear();
      const invoiceMonth = invoiceDate.getMonth();

      acc.total += total;

      if (invoiceYear === currentYear) {
        acc.total_year += total;
      }

      if (invoiceYear === currentYear && invoiceMonth === currentMonth) {
        acc.total_month += total;
      }

      if (invoiceYear === lastMonthYear && invoiceMonth === lastMonth) {
        acc.total_last_month += total;
      }

      return acc;
    }, { ...EMPTY_SUMMARY });
  };

  const calculateSummaryCounts = (items: InvoiceRead[]): InvoiceSummaryCounts => {
    const now = new Date();
    const currentYear = now.getFullYear();
    const currentMonth = now.getMonth();
    const lastMonthDate = new Date(currentYear, currentMonth - 1, 1);
    const lastMonthYear = lastMonthDate.getFullYear();
    const lastMonth = lastMonthDate.getMonth();

    return items.reduce<InvoiceSummaryCounts>((acc, invoice) => {
      const invoiceDate = new Date(`${invoice.i_date}T00:00:00`);
      const invoiceYear = invoiceDate.getFullYear();
      const invoiceMonth = invoiceDate.getMonth();

      acc.total += 1;

      if (invoiceYear === currentYear) {
        acc.total_year += 1;
      }

      if (invoiceYear === currentYear && invoiceMonth === currentMonth) {
        acc.total_month += 1;
      }

      if (invoiceYear === lastMonthYear && invoiceMonth === lastMonth) {
        acc.total_last_month += 1;
      }

      return acc;
    }, { ...EMPTY_SUMMARY_COUNTS });
  };

  const openInvoicePdf = async (invoiceId: string) => {
    try {
      const res = await api.get(`/invoices/${invoiceId}/pdf`, {
        responseType: "blob",
      });
      const blobUrl = URL.createObjectURL(new Blob([res.data], { type: "application/pdf" }));
      setPdfUrl(blobUrl);
    } catch (err) {
      console.error(err);
      alert("Could not open PDF. Please try again.");
    }
  };

  const refreshSummary = async (fallbackInvoices: InvoiceRead[]) => {
    setSummary(calculateSummary(fallbackInvoices));
    setSummaryCounts(calculateSummaryCounts(fallbackInvoices));

    try {
      const summaryRes = await api.get<InvoiceSummaryRead>("/invoices/summary");
      setSummary(normalizeSummary(summaryRes.data));
    } catch (err) {
      console.error("Could not load invoice summary", err);
    }
  };

  const fetchInvoices = async () => {
    setLoading(true);
    try {
      const invoicesRes = await api.get<InvoiceRead[]>("/invoices");
      setInvoices(invoicesRes.data);
      await refreshSummary(invoicesRes.data);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchInvoices();
  }, []);

  useEffect(() => {
    setCurrentPage((page) => Math.min(page, totalPages));
  }, [totalPages]);

  const fetchNextSerie = useCallback(async (invoiceDate: string) => {
    const res = await api.get<{ i_serie: string }>("/invoices/next-serie", {
      params: { serie_date: invoiceDate },
    });
    return res.data.i_serie;
  }, []);

  const handleCreateInvoice = async (invoice: InvoiceCreate) => {
    const res = await api.post<InvoiceRead>("/invoices", invoice);
    const nextInvoices = [res.data, ...invoices];
    setInvoices(nextInvoices);
    await refreshSummary(nextInvoices);
    setCurrentPage(1);
    await openInvoicePdf(res.data.i_id);
  };

  const buildEditableInvoice = (
    invoice: InvoiceRead,
    details: InvoiceDetailCreate[] = [
      {
        id_number: 1,
        id_description: "Appraisal Report",
        id_qty: 1,
        id_rate: invoice.i_total,
        id_sale_tax: 0,
      },
    ]
  ): InvoiceCreate => ({
    i_name: invoice.i_name,
    i_inscription: invoice.i_inscription ?? undefined,
    i_email: invoice.i_email ?? undefined,
    i_address: invoice.i_address ?? undefined,
    i_serie: invoice.i_serie ?? undefined,
    i_date: invoice.i_date,
    i_billto: invoice.i_billto ?? undefined,
    i_total: invoice.i_total,
    i_is_pay: invoice.i_is_pay,
    details,
  });

  const openEditInvoice = async (invoice: InvoiceRead) => {
    setEditingInvoiceId(invoice.i_id);
    setEditingInvoice(buildEditableInvoice(invoice));
    setModalOpen(true);

    try {
      const res = await api.get<InvoiceWithDetailsRead>(`/invoices/${invoice.i_id}`);
      const details = res.data.details.length
        ? res.data.details.map((detail) => ({
              id_number: detail.id_number,
              id_description: detail.id_description,
              id_qty: detail.id_qty,
              id_rate: detail.id_rate,
              id_sale_tax: detail.id_sale_tax,
              id_adress: detail.id_adress,
              id_adress2: detail.id_adress2,
            }))
        : undefined;

      setEditingInvoice(buildEditableInvoice(res.data, details));
    } catch (err) {
      console.error(err);
    }
  };

  const handleSaveInvoice = async (invoice: InvoiceCreate) => {
    if (!editingInvoiceId) {
      await handleCreateInvoice(invoice);
      return;
    }

    const res = await api.put<InvoiceRead>(`/invoices/${editingInvoiceId}`, invoice);
    const nextInvoices = invoices.map((item) =>
      item.i_id === editingInvoiceId ? res.data : item
    );
    setInvoices(nextInvoices);
    await refreshSummary(nextInvoices);
    await openInvoicePdf(res.data.i_id);
    setEditingInvoiceId(null);
    setEditingInvoice(null);
  };

  const closeInvoiceModal = () => {
    setModalOpen(false);
    setEditingInvoiceId(null);
    setEditingInvoice(null);
  };

  const handleLogout = () => {
    logout();
    window.location.href = "/login";
  };

  const renderSummaryItem = (
    label: string,
    key: SummaryKey,
    value: number,
    count: number
  ) => {
    const breakdown = summaryBreakdown[key];

    return (
      <div className="summary-item" tabIndex={0}>
        <span>{label}</span>
        <strong>
          {formatCurrency(value)} <small>({count})</small>
        </strong>
        <div className="summary-tooltip" role="tooltip">
          <div>
            <span>Paid</span>
            <strong>
              {formatCurrency(breakdown.paidTotal)} <small>({breakdown.paidCount})</small>
            </strong>
          </div>
          <div>
            <span>Pending</span>
            <strong>
              {formatCurrency(breakdown.pendingTotal)}{" "}
              <small>({breakdown.pendingCount})</small>
            </strong>
          </div>
        </div>
      </div>
    );
  };

  return (
    <div className="app-bg min-h-screen">
      <header className="app-header">
        <div className="header-left">
          <div className="logo-box">
            <span className="logo-text">O</span>
          </div>
          <div>
            <div className="header-title">RMCP</div>
            <div className="header-subtitle">Raimundo Marrero - Tasador</div>
          </div>
        </div>
        <div className="header-right">
          <button
            className="btn-secondary btn-icon-label mr-2"
            onClick={() => {
              setEditingInvoiceId(null);
              setEditingInvoice(null);
              setModalOpen(true);
            }}
          >
            <span className="material-icons" aria-hidden="true">
              add
            </span>
            New invoice
          </button>
          <button className="btn-outline btn-icon-label" onClick={handleLogout}>
            <span className="material-icons" aria-hidden="true">
              logout
            </span>
            Logout
          </button>
        </div>
      </header>

      <main className="app-main">
        <div className="card">
          <div className="card-header">
            <h2>Invoices</h2>
            <div className="invoice-table-toolbar">
              {loading && <span className="muted">Loading...</span>}
              <label className="page-size-control">
                <span>Rows</span>
                <select
                  value={pageSize}
                  onChange={(event) => {
                    setPageSize(Number(event.target.value));
                    setCurrentPage(1);
                  }}
                >
                  {PAGE_SIZE_OPTIONS.map((option) => (
                    <option key={option} value={option}>
                      {option}
                    </option>
                  ))}
                </select>
              </label>
            </div>
          </div>
          <div className="card-body">
            {invoices.length === 0 ? (
              <div className="table-empty-state">
                <span className="material-icons" aria-hidden="true">
                  receipt_long
                </span>
                <strong>No invoices found</strong>
                <p>Create the first invoice to start tracking totals.</p>
              </div>
            ) : (
              <>
                <table className="table">
                  <thead>
                    <tr>
                      <th>Date</th>
                      <th>Serie</th>
                      <th>Bill to</th>
                      <th className="text-right">Total</th>
                      <th className="text-center">Paid</th>
                      <th className="text-center">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {pagedInvoices.map((inv) => (
                      <tr key={inv.i_id}>
                        <td>{inv.i_date}</td>
                        <td className="serie-cell">{inv.i_serie}</td>
                        <td>{inv.i_billto ?? "-"}</td>
                        <td className="amount-cell">{formatCurrency(inv.i_total)}</td>
                        <td className="text-center">
                          <span className={`status-badge ${inv.i_is_pay ? "paid" : "unpaid"}`}>
                            {inv.i_is_pay ? "Paid" : "Pending"}
                          </span>
                        </td>
                        <td className="actions-cell">
                          <div className="table-actions">
                            <button
                              className="icon-button"
                              type="button"
                              title="Edit invoice"
                              aria-label="Edit invoice"
                              onClick={() => openEditInvoice(inv)}
                            >
                              <span className="material-icons" aria-hidden="true">
                                edit
                              </span>
                            </button>
                            <button
                              className="icon-button"
                              type="button"
                              title="View PDF"
                              aria-label="View PDF"
                              onClick={() => openInvoicePdf(inv.i_id)}
                            >
                              <span className="material-icons" aria-hidden="true">
                                picture_as_pdf
                              </span>
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <div className="table-pagination">
                  <span>
                    Page {currentPage} of {totalPages}
                  </span>
                  <div className="pagination-actions">
                    <button
                      className="btn-outline"
                      type="button"
                      disabled={currentPage === 1}
                      onClick={() => setCurrentPage((page) => Math.max(1, page - 1))}
                    >
                      Previous
                    </button>
                    <button
                      className="btn-outline"
                      type="button"
                      disabled={currentPage === totalPages}
                      onClick={() =>
                        setCurrentPage((page) => Math.min(totalPages, page + 1))
                      }
                    >
                      Next
                    </button>
                  </div>
                </div>
              </>
            )}
          </div>
        </div>
      </main>

      <footer className="invoice-summary-footer">
        {renderSummaryItem("Total", "total", summary.total, summaryCounts.total)}
        {renderSummaryItem(
          "Total year",
          "total_year",
          summary.total_year,
          summaryCounts.total_year
        )}
        {renderSummaryItem(
          "Total month",
          "total_month",
          summary.total_month,
          summaryCounts.total_month
        )}
        {renderSummaryItem(
          "Total last month",
          "total_last_month",
          summary.total_last_month,
          summaryCounts.total_last_month
        )}
      </footer>

      {pdfUrl && (
        <div className="modal-overlay">
          <div className="modal-card modal-card-lg">
            <div className="modal-header">
              <h2>Invoice PDF</h2>
              <button
                className="modal-close"
                onClick={() => {
                  URL.revokeObjectURL(pdfUrl);
                  setPdfUrl(null);
                }}
              >
                ×
              </button>
            </div>
            <div className="modal-body" style={{ height: "75vh" }}>
              <iframe
                src={pdfUrl}
                title="Invoice PDF"
                style={{ width: "100%", height: "100%", border: "none" }}
              />
            </div>
          </div>
        </div>
      )}

      <InvoiceModal
        open={modalOpen}
        onClose={closeInvoiceModal}
        onSubmit={handleSaveInvoice}
        initialInvoice={editingInvoice}
        mode={editingInvoiceId ? "edit" : "create"}
        onRequestSerie={fetchNextSerie}
      />
    </div>
  );
};

export default DashboardPage;
