// src/pages/DashboardPage.tsx
import React, { useEffect, useState } from "react";
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
  i_u_id: string;
  i_create_at: string;
}

const DashboardPage: React.FC = () => {
  const { logout } = useAuth();
  const [invoices, setInvoices] = useState<InvoiceRead[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [pdfUrl, setPdfUrl] = useState<string | null>(null);

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

  const fetchInvoices = async () => {
    setLoading(true);
    try {
      const res = await api.get<InvoiceRead[]>("/invoices");
      setInvoices(res.data);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchInvoices();
  }, []);

  const handleCreateInvoice = async (invoice: InvoiceCreate) => {
    const res = await api.post<InvoiceRead>("/invoices", invoice);
    setInvoices((prev) => [res.data, ...prev]);
    await openInvoicePdf(res.data.i_id);
  };

  const handleLogout = () => {
    logout();
    window.location.href = "/login";
  };

  return (
    <div className="app-bg min-h-screen">
      <header className="app-header">
        <div className="header-left">
          <div className="logo-box">
            {/* Reemplaza por tu imagen real */}
            <span className="logo-text">O</span>
          </div>
          <div>
            <div className="header-title">Octagon Invoice Dashboard</div>
            <div className="header-subtitle">Raimundo Marrero - Tasador</div>
          </div>
        </div>
        <div className="header-right">
          <button className="btn-secondary mr-2" onClick={() => setModalOpen(true)}>
            New invoice
          </button>
          <button className="btn-outline" onClick={handleLogout}>
            Logout
          </button>
        </div>
      </header>

      <main className="app-main">
        <div className="card">
          <div className="card-header">
            <h2>Invoices</h2>
            {loading && <span className="muted">Loading...</span>}
          </div>
          <div className="card-body">
            {invoices.length === 0 ? (
              <div className="muted">No invoices found. Create the first one.</div>
            ) : (
              <table className="table">
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>Serie</th>
                    <th>Bill to</th>
                    <th>Total</th>
                    <th>Created at</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {invoices.map((inv) => (
                    <tr key={inv.i_id}>
                      <td>{inv.i_date}</td>
                      <td>{inv.i_serie}</td>
                      <td>{inv.i_billto ?? "-"}</td>
                      <td>{inv.i_total.toFixed(2)}</td>
                      <td>{new Date(inv.i_create_at).toLocaleString()}</td>
                      <td>
                        <button
                          className="btn-link"
                          onClick={() => openInvoicePdf(inv.i_id)}
                        >
                          View PDF
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      </main>

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
        onClose={() => setModalOpen(false)}
        onSubmit={handleCreateInvoice}
      />
    </div>
  );
};

export default DashboardPage;
