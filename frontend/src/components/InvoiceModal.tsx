// src/components/InvoiceModal.tsx
import React, { useEffect, useMemo, useState } from "react";
import { InvoiceCreate } from "../pages/DashboardPage";

interface Props {
  open: boolean;
  onClose: () => void;
  onSubmit: (invoice: InvoiceCreate) => Promise<void>;
  initialInvoice?: InvoiceCreate | null;
  mode?: "create" | "edit";
  onRequestSerie?: (invoiceDate: string) => Promise<string>;
}

const InvoiceModal: React.FC<Props> = ({
  open,
  onClose,
  onSubmit,
  initialInvoice = null,
  mode = "create",
  onRequestSerie,
}) => {
  const [client, setClient] = useState("");
  const [address, setAddress] = useState("");
  const [address2, setAddress2] = useState("");
  const [serie, setSerie] = useState("");
  const today = useMemo(() => new Date().toISOString().slice(0, 10), []);
  const [date, setDate] = useState(today);
  const [rate, setRate] = useState("0");
  const [qty, setQty] = useState<number>(1);
  const [isPay, setIsPay] = useState(false);
  const [loading, setLoading] = useState(false);

  const rateNumber = parseFloat(rate);
  const safeRate = Number.isFinite(rateNumber) ? rateNumber : 0;
  const total = qty * safeRate;
  const canSave =
    client.trim() !== "" &&
    date.trim() !== "" &&
    address.trim() !== "" &&
    Number.isFinite(qty) &&
    qty > 0 &&
    Number.isFinite(rateNumber) &&
    rateNumber > 0 &&
    serie.trim() !== "";

  const requestSerieForDate = (invoiceDate: string) => {
    if (mode !== "create") return;

    setSerie("");
    onRequestSerie?.(invoiceDate)
      .then((nextSerie) => {
        setSerie(nextSerie);
      })
      .catch((err) => {
        console.error(err);
        setSerie(`${invoiceDate}-001`);
      });
  };

  useEffect(() => {
    if (open) {
      let cancelled = false;
      const firstDetail = initialInvoice?.details?.[0];
      const nextDate = initialInvoice?.i_date ?? today;

      setClient(initialInvoice?.i_billto ?? "");
      setAddress(firstDetail?.id_adress ?? "");
      setAddress2(firstDetail?.id_adress2 ?? "");
      setSerie(initialInvoice?.i_serie ?? "");
      setDate(nextDate);
      setQty(firstDetail?.id_qty ?? 1);
      setRate(String(firstDetail?.id_rate ?? 0));
      setIsPay(initialInvoice?.i_is_pay ?? false);

      if (!initialInvoice?.i_serie && mode === "create") {
        setSerie("");
        onRequestSerie?.(nextDate)
          .then((nextSerie) => {
            if (!cancelled) {
              setSerie(nextSerie);
            }
          })
          .catch((err) => {
            console.error(err);
            if (!cancelled) {
              setSerie(`${today}-001`);
            }
          });
      }

      return () => {
        cancelled = true;
      };
    }
  }, [initialInvoice, mode, onRequestSerie, open, today]);

  if (!open) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      await onSubmit({
        i_name: "Raimundo Marrero - TASADOR",
        i_inscription: "EPA 780 -CGA 195",
        i_email: "raimundo.marrero2@gmail.com",
        i_address: "Cond. El Centro | 500 Muñoz Rivera Ste 301 San Juan, PR 00918",
        i_serie: serie,
        i_date: date,
        i_billto: client,
        i_total: total,
        i_is_pay: isPay,
        details: [
          {
            id_number: 1,
            id_description: "Appraisal Report",
            id_qty: qty,
            id_rate: safeRate,
            id_sale_tax: 0,
            id_adress: address,
            id_adress2: address2,
          },
        ],
      });
      onClose();
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="modal-overlay">
      <div className="modal-card">
        <div className="modal-header">
          <div>
            <h2>{mode === "edit" ? "Edit Invoice" : "New Invoice"}</h2>
            <p>{mode === "edit" ? "Update invoice details and payment status." : "Create a new invoice record."}</p>
          </div>
          <button className="modal-close" onClick={onClose}>
            ×
          </button>
        </div>
        <form onSubmit={handleSubmit} className="modal-body">
          <div className="invoice-form-section">
            <div className="section-title">
              <span className="material-icons" aria-hidden="true">person</span>
              Client
            </div>
            <div className="grid-2">
              <label className="form-label">
                Bill to
                <input
                  className="form-input"
                  value={client}
                  onChange={(e) => setClient(e.target.value)}
                  required
                />
              </label>
              <label className="form-label">
                Serie {mode === "create" ? "(auto)" : ""}
                <input
                  className="form-input"
                  value={serie}
                  readOnly={mode === "create"}
                  onChange={(e) => setSerie(e.target.value)}
                  required
                />
              </label>
            </div>

            <div className="grid-2 mt-3">
              <label className="form-label">
                Date
                <input
                  type="date"
                  className="form-input"
                  value={date}
                  onChange={(e) => {
                    const nextDate = e.target.value;
                    setDate(nextDate);
                    requestSerieForDate(nextDate);
                  }}
                  required
                />
              </label>
              <div />
            </div>

            <label className="form-label mt-3">
              Address
              <input
                className="form-input"
                value={address}
                onChange={(e) => setAddress(e.target.value)}
                required
              />
            </label>

            <label className="form-label mt-3">
              Address 2
              <input
                className="form-input"
                value={address2}
                onChange={(e) => setAddress2(e.target.value)}
              />
            </label>
          </div>

          <div className="invoice-form-section">
            <div className="section-title">
              <span className="material-icons" aria-hidden="true">request_quote</span>
              Invoice amount
            </div>
            <div className="grid-3">
              <label className="form-label">
                Qty
                <input
                  type="number"
                  className="form-input"
                  value={qty}
                  min={0.01}
                  step={0.01}
                  onChange={(e) => setQty(parseFloat(e.target.value))}
                  required
                />
              </label>
              <label className="form-label">
                Rate
                <input
                  type="number"
                  className="form-input"
                  value={rate}
                  min={0.01}
                  step={0.01}
                  onFocus={() => {
                    if (rate === "0") {
                      setRate("");
                    }
                  }}
                  onChange={(e) => setRate(e.target.value)}
                  required
                />
              </label>
              <div className="invoice-total-box">
                <span>Total</span>
                <strong>
                  {total.toLocaleString("en-US", {
                    style: "currency",
                    currency: "USD",
                    minimumFractionDigits: 2,
                  })}
                </strong>
              </div>
            </div>

            <label className="paid-toggle mt-3">
              <input
                type="checkbox"
                checked={isPay}
                onChange={(e) => setIsPay(e.target.checked)}
              />
              <span aria-hidden="true" />
              Mark invoice as paid
            </label>
          </div>

          <div className="modal-actions">
            <button type="button" className="btn-outline" onClick={onClose}>
              Cancel
            </button>
            <button type="submit" className="btn-primary" disabled={loading || !canSave}>
              {loading ? "Saving..." : mode === "edit" ? "Update invoice" : "Save invoice"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default InvoiceModal;
