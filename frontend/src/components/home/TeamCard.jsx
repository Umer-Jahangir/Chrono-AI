
export default function TeamCard({ member }) {
  return (
    <div className="group bg-surface rounded-2xl overflow-hidden border border-outline-variant/30 hover:border-primary/50 hover:shadow-lg transition-all duration-300 shadow-sm">
      <div className="aspect-square overflow-hidden bg-surface-container-low">
        <img
          src={member.image}
          alt={member.name}
          className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"
        />
      </div>
      <div className="p-4 text-center">
        <h3 className="text-base font-semibold text-on-surface mb-1">{member.name}</h3>
        <p className="text-xs text-primary font-bold tracking-wide">{member.role}</p>
      </div>
    </div>
  );
}
